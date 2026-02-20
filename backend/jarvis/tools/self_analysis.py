"""
Self-analysis tool — JARVIS can run diagnostics on its own capabilities.
Reports: LLM provider availability, tool health, budget status, Grok connectivity.
Useful for debugging "chat not responding" or "email not responding" issues.
"""
import asyncio
from jarvis.tools.base import Tool, ToolResult
from jarvis.config import settings
from jarvis.observability.logger import get_logger

log = get_logger("tools.self_analysis")


class SelfAnalysisTool(Tool):
    """Run self-diagnostics: check LLM providers, tools, Grok, email config."""

    name = "self_analysis"
    description = (
        "Run self-diagnostics on JARVIS capabilities. "
        "Reports: which LLM providers are available, Grok connectivity, "
        "email config, tool count, budget status. "
        "Use when debugging 'chat not responding' or 'email not responding'."
    )
    timeout_seconds = 30

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "check": {
                        "type": "string",
                        "description": "What to check: all, providers, grok, email, tools, budget",
                        "enum": ["all", "providers", "grok", "email", "tools", "budget"],
                        "default": "all",
                    },
                },
            },
        }

    def __init__(self, llm_router=None, budget_tracker=None):
        self.router = llm_router
        self.budget = budget_tracker

    async def execute(
        self,
        check: str = "all",
        **kwargs,
    ) -> ToolResult:
        """
        Run diagnostics.

        Args:
            check: One of "all", "providers", "grok", "email", "tools", "budget"

        Returns:
            ToolResult with diagnostic report.
        """
        checks = ("all", "providers", "grok", "email", "tools", "budget")
        if check not in checks:
            return ToolResult(
                success=False,
                output="",
                error=f"Unknown check: {check}. Use one of: {', '.join(checks)}",
            )

        lines = ["# JARVIS Self-Analysis Report\n"]

        try:
            if check in ("all", "providers"):
                lines.append(await self._check_providers())
            if check in ("all", "grok"):
                lines.append(await self._check_grok())
            if check in ("all", "email"):
                lines.append(self._check_email())
            if check in ("all", "tools"):
                lines.append(await self._check_tools())
            if check in ("all", "budget"):
                lines.append(await self._check_budget())

            return ToolResult(success=True, output="\n".join(lines), error=None)
        except Exception as e:
            log.error("self_analysis_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))

    async def _check_providers(self) -> str:
        lines = ["## LLM Providers\n"]
        if not self.router:
            lines.append("- Router not available (tool not wired)\n")
            return "\n".join(lines)

        available = self.router.get_available_providers()
        lines.append(f"- Available: {', '.join(available) or 'none'}\n")

        tier_info = self.router.get_tier_info()
        for tier, models in list(tier_info.items())[:4]:
            avail = [f"{m['provider']}/{m['model']}" for m in models if m.get("available")]
            if avail:
                lines.append(f"- {tier}: {', '.join(avail[:3])}{'...' if len(avail) > 3 else ''}\n")
        return "\n".join(lines)

    async def _check_grok(self) -> str:
        lines = ["## Grok (xAI)\n"]
        has_key = bool(settings.grok_api_key)
        lines.append(f"- API key configured: {has_key}\n")

        if not has_key:
            lines.append("- Set GROK_API_KEY in .env to enable Grok.\n")
            return "\n".join(lines)

        # Quick connectivity test
        try:
            from jarvis.llm.providers.grok import GrokProvider
            provider = GrokProvider()
            if provider.is_available():
                resp = await provider.complete(
                    messages=[{"role": "user", "content": "Say OK"}],
                    model="grok-3-mini",
                    max_tokens=5,
                )
                lines.append(f"- Connectivity: OK (tokens: {resp.total_tokens})\n")
            else:
                lines.append("- Connectivity: Provider reports not available\n")
        except Exception as e:
            lines.append(f"- Connectivity: FAILED — {str(e)}\n")
        return "\n".join(lines)

    def _check_email(self) -> str:
        lines = ["## Email\n"]
        has_addr = bool(settings.gmail_address)
        has_app = bool(settings.gmail_app_password)
        listener = getattr(settings, "email_listener_enabled", False)
        lines.append(f"- Gmail address: {'set' if has_addr else 'NOT SET'}\n")
        lines.append(f"- App password: {'set' if has_app else 'NOT SET (required for IMAP/SMTP)'}\n")
        lines.append(f"- Email listener enabled: {listener}\n")
        if not has_app:
            lines.append("- For email: enable 2FA, create App Password, set GMAIL_APP_PASSWORD.\n")
        return "\n".join(lines)

    async def _check_tools(self) -> str:
        lines = ["## Tools\n"]
        if self.router:
            # Router has no tool list; tools are in ToolRegistry
            lines.append("- Check /api/tools for registered tools.\n")
        return "\n".join(lines)

    async def _check_budget(self) -> str:
        lines = ["## Budget\n"]
        if not self.budget:
            lines.append("- Budget tracker not available\n")
            return "\n".join(lines)

        try:
            status = await self.budget.get_status()
            lines.append(f"- Remaining: ${status.get('remaining', 0):.2f}\n")
            lines.append(f"- Spent: ${status.get('spent', 0):.2f}\n")
            lines.append(f"- Percent used: {status.get('percent_used', 0):.1f}%\n")
        except Exception as e:
            lines.append(f"- Error: {e}\n")
        return "\n".join(lines)
