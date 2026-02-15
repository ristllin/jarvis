"""
resource_manager tool — allows JARVIS to view and manage API provider resources.
JARVIS can check balances, add API keys, update known balances, and add new providers.
"""
import json
from jarvis.tools.base import Tool, ToolResult
from jarvis.budget.tracker import BudgetTracker
from jarvis.observability.logger import get_logger

log = get_logger("tools.resource_manager")


class ResourceManagerTool(Tool):
    name = "resource_manager"
    description = (
        "View and manage API provider resources. Check per-provider balances, "
        "update known account balances, add new API keys, or add new providers. "
        "Actions: 'view' (see all providers), 'update' (update a provider's balance/info), "
        "'add' (add a new provider with API key)."
    )
    timeout_seconds = 15

    def __init__(self, budget_tracker: BudgetTracker):
        self.budget = budget_tracker

    async def execute(self, action: str = "view", **kwargs) -> ToolResult:
        try:
            if action == "view":
                return await self._view()
            elif action == "update":
                return await self._update(**kwargs)
            elif action == "add":
                return await self._add(**kwargs)
            else:
                return ToolResult(
                    success=False, output="",
                    error=f"Unknown action: {action}. Use: view, update, add",
                )
        except Exception as e:
            log.error("resource_manager_error", action=action, error=str(e))
            return ToolResult(success=False, output="", error=str(e))

    async def _view(self) -> ToolResult:
        status = await self.budget.get_status()
        providers = status.get("providers", [])

        lines = [
            f"=== Resource Overview ===",
            f"Total spent this month: ${status['spent']:.4f}",
            f"Estimated total remaining: ${status['remaining']:.2f}",
            f"",
        ]

        for p in providers:
            name = p["provider"].upper()
            tier = p["tier"]
            spent = p["spent_tracked"]
            balance = p.get("known_balance")
            remaining = p.get("estimated_remaining")
            notes = p.get("notes", "")

            lines.append(f"── {name} ({tier}) ──")
            if balance is not None:
                lines.append(f"  Known balance: ${balance:.2f}")
                lines.append(f"  Spent (tracked): ${spent:.4f}")
                lines.append(f"  Estimated remaining: ${remaining:.2f}")
            else:
                lines.append(f"  Balance: unknown")
                lines.append(f"  Spent (tracked): ${spent:.4f}")
            if notes:
                lines.append(f"  Notes: {notes}")
            updated = p.get("balance_updated_at")
            if updated:
                lines.append(f"  Balance last updated: {updated}")
            lines.append("")

        return ToolResult(success=True, output="\n".join(lines))

    async def _update(self, provider: str = None, known_balance: float = None,
                      tier: str = None, notes: str = None,
                      reset_spending: bool = False, **kwargs) -> ToolResult:
        if not provider:
            return ToolResult(success=False, output="", error="'provider' is required")

        result = await self.budget.update_provider_balance(
            provider=provider,
            known_balance=known_balance,
            tier=tier,
            notes=notes,
            reset_spending=reset_spending,
        )
        return ToolResult(
            success=True,
            output=f"Updated {provider}: {json.dumps(result, default=str)}",
        )

    async def _add(self, provider: str = None, api_key: str = None,
                   known_balance: float = None, tier: str = "unknown",
                   notes: str = None, **kwargs) -> ToolResult:
        if not provider:
            return ToolResult(success=False, output="", error="'provider' is required")

        result = await self.budget.add_provider(
            provider=provider,
            api_key=api_key,
            known_balance=known_balance,
            tier=tier,
            notes=notes,
        )

        msg = f"Added/updated provider '{provider}'"
        if api_key:
            msg += " (API key set)"
        if known_balance is not None:
            msg += f" with balance ${known_balance:.2f}"
        return ToolResult(success=True, output=msg)

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "action": {
                    "type": "string",
                    "description": "'view' to see all providers, 'update' to update balance/info, 'add' to add provider",
                    "enum": ["view", "update", "add"],
                },
                "provider": {
                    "type": "string",
                    "description": "Provider name (e.g. anthropic, openai, mistral, tavily, ollama)",
                },
                "api_key": {
                    "type": "string",
                    "description": "API key for the provider (for 'add' action)",
                },
                "known_balance": {
                    "type": "number",
                    "description": "Known account balance in USD",
                },
                "tier": {
                    "type": "string",
                    "description": "Provider tier: paid, free, unknown",
                },
                "notes": {
                    "type": "string",
                    "description": "Notes about the provider (e.g. rate limits, tier info)",
                },
                "reset_spending": {
                    "type": "boolean",
                    "description": "Reset tracked spending to 0 when updating balance (use when you've confirmed exact current balance)",
                },
            },
            "required": ["action"],
        }
