"""
CreditMonitorTool — checks remaining credits for all API providers.
Provides a structured format for monitoring resource status.
"""

import json

from jarvis.budget.tracker import CURRENCY_SYMBOLS, BudgetTracker
from jarvis.observability.logger import get_logger
from jarvis.tools.base import Tool, ToolResult

log = get_logger("tools.credit_monitor")


class CreditMonitorTool(Tool):
    name = "credit_monitor"
    description = (
        "Check remaining credits for all API providers. "
        "Returns structured data on provider balances, spending, and estimated remaining credits."
    )
    timeout_seconds = 10

    def __init__(self, budget_tracker: BudgetTracker):
        self.budget = budget_tracker

    async def execute(self, format: str = "json", **kwargs) -> ToolResult:
        """
        Check remaining credits for all providers.

        Args:
            format: Output format. Options: 'json', 'text', 'markdown'
        """
        try:
            status = await self.budget.get_status()
            providers = status.get("providers", [])

            # Format based on requested format
            if format == "json":
                output = {
                    "total_spent_usd": status["spent"],
                    "total_remaining_usd": status["remaining"],
                    "providers": [],
                }
                for p in providers:
                    output["providers"].append(
                        {
                            "provider": p["provider"],
                            "tier": p["tier"],
                            "currency": p["currency"],
                            "known_balance": p["known_balance"],
                            "spent": p["spent_tracked"],
                            "remaining": p["estimated_remaining"],
                            "last_updated": p["balance_updated_at"],
                            "notes": p["notes"],
                        }
                    )
                return ToolResult(success=True, output=json.dumps(output, indent=2))

            if format == "markdown":
                lines = [
                    "# API Provider Credit Status",
                    "",
                    f"- **Total spent (USD):** ${status['spent']:.4f}",
                    f"- **Total remaining (USD):** ${status['remaining']:.2f}",
                    "",
                    "## Provider Details",
                    "",
                ]

                for p in providers:
                    name = p["provider"].upper()
                    tier = p["tier"]
                    currency = p["currency"]
                    balance = p["known_balance"]
                    spent = p["spent_tracked"]
                    remaining = p["estimated_remaining"]
                    notes = p["notes"]

                    lines.append(f"### {name} ({tier})")
                    if balance is not None:
                        lines.append(f"- **Balance:** {self._fmt(balance, currency)}")
                        lines.append(
                            f"- **Spent:** {self._fmt(spent, currency, 4 if currency in ('USD', 'EUR', 'GBP') else 0)}"
                        )
                        lines.append(f"- **Remaining:** {self._fmt(remaining, currency)}")
                    else:
                        lines.append("- **Balance:** Unknown")
                        lines.append(
                            f"- **Spent:** {self._fmt(spent, currency, 4 if currency in ('USD', 'EUR', 'GBP') else 0)}"
                        )

                    if notes:
                        lines.append(f"- **Notes:** {notes}")

                    updated = p["balance_updated_at"]
                    if updated:
                        lines.append(f"- **Last Updated:** {updated}")
                    lines.append("")

                return ToolResult(success=True, output="\n".join(lines))

            # text format (default)
            lines = [
                "=== Credit Status ===",
                f"Total spent (USD): ${status['spent']:.4f}",
                f"Total remaining (USD): ${status['remaining']:.2f}",
                "",
            ]

            for p in providers:
                name = p["provider"].upper()
                tier = p["tier"]
                currency = p["currency"]
                balance = p["known_balance"]
                spent = p["spent_tracked"]
                remaining = p["estimated_remaining"]
                notes = p["notes"]

                lines.append(f"── {name} ({tier}, {currency}) ──")
                if balance is not None:
                    lines.append(f"  Balance: {self._fmt(balance, currency)}")
                    lines.append(
                        f"  Spent: {self._fmt(spent, currency, 4 if currency in ('USD', 'EUR', 'GBP') else 0)}"
                    )
                    lines.append(f"  Remaining: {self._fmt(remaining, currency)}")
                else:
                    lines.append("  Balance: Unknown")
                    lines.append(
                        f"  Spent: {self._fmt(spent, currency, 4 if currency in ('USD', 'EUR', 'GBP') else 0)}"
                    )

                if notes:
                    lines.append(f"  Notes: {notes}")

                updated = p["balance_updated_at"]
                if updated:
                    lines.append(f"  Last Updated: {updated}")
                lines.append("")

            return ToolResult(success=True, output="\n".join(lines))

        except Exception as e:
            log.error("credit_monitor_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))

    def _fmt(self, value: float, currency: str, decimals: int = 2) -> str:
        """Format a value with its currency symbol/unit."""
        sym = CURRENCY_SYMBOLS.get(currency, "")
        if currency in ("USD", "EUR", "GBP"):
            return f"{sym}{value:.{decimals}f}"
        # Non-monetary: "989 credits", "150 requests"
        return f"{value:.0f} {currency}"

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "format": {
                    "type": "string",
                    "description": "Output format: 'json', 'text', or 'markdown'",
                    "enum": ["json", "text", "markdown"],
                    "default": "text",
                }
            },
        }
