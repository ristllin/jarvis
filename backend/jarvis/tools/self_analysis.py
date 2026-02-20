"""
Self-analysis tool — JARVIS can run diagnostics on its own capabilities.
Supports both config checks (fast) and functional round-trip tests (thorough).
"""

import asyncio
import os
import time
import uuid

from jarvis.config import settings
from jarvis.observability.logger import get_logger
from jarvis.tools.base import Tool, ToolResult

log = get_logger("tools.self_analysis")


class SelfAnalysisTool(Tool):
    name = "self_analysis"
    description = (
        "Run self-diagnostics: config checks (providers, email, tools, budget) "
        "or functional round-trip tests (email send+fetch, telegram, LLM ping, "
        "vector write+search, file I/O, news). Use check=functional for thorough testing."
    )
    timeout_seconds = 90

    VALID_CHECKS = (
        "all",
        "providers",
        "grok",
        "email",
        "tools",
        "budget",
        "telegram",
        "functional",
        "functional_email",
        "functional_telegram",
        "functional_llm",
        "functional_memory",
        "functional_news",
        "health",
    )

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "check": {
                    "type": "string",
                    "description": f"What to check: {', '.join(self.VALID_CHECKS)}",
                    "default": "all",
                },
            },
            "required": [],
        }

    def __init__(self, llm_router=None, budget_tracker=None):
        self.router = llm_router
        self.budget = budget_tracker

    async def execute(self, check: str = "all", **kwargs) -> ToolResult:
        if check not in self.VALID_CHECKS:
            return ToolResult(
                success=False,
                output="",
                error=f"Unknown check: {check}. Use one of: {', '.join(self.VALID_CHECKS)}",
            )

        lines = ["# JARVIS Self-Analysis Report\n"]
        try:
            # Config checks
            if check in ("all", "providers"):
                lines.append(await self._check_providers())
            if check in ("all", "grok"):
                lines.append(await self._check_grok())
            if check in ("all", "email"):
                lines.append(self._check_email_config())
            if check in ("all", "telegram"):
                lines.append(self._check_telegram_config())
            if check in ("all", "tools"):
                lines.append(self._check_tools())
            if check in ("all", "budget"):
                lines.append(await self._check_budget())

            # Functional tests
            if check in ("functional", "functional_email"):
                lines.append(await self._functional_email())
            if check in ("functional", "functional_telegram"):
                lines.append(await self._functional_telegram())
            if check in ("functional", "functional_llm"):
                lines.append(await self._functional_llm())
            if check in ("functional", "functional_memory"):
                lines.append(await self._functional_memory())
            if check in ("functional", "functional_news"):
                lines.append(await self._functional_news())

            # System health
            if check in ("health", "functional"):
                lines.append(self._check_system_health())

            return ToolResult(success=True, output="\n".join(lines))
        except Exception as e:
            log.error("self_analysis_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))

    # ── Config Checks ──────────────────────────────────────────────────

    async def _check_providers(self) -> str:
        lines = ["## LLM Providers\n"]
        if not self.router:
            return "## LLM Providers\n- Router not available\n"
        available = self.router.get_available_providers()
        lines.append(f"- Available: {', '.join(available) or 'none'}\n")
        tier_info = self.router.get_tier_info()
        for tier, models in list(tier_info.items())[:4]:
            avail = [f"{m['provider']}/{m['model']}" for m in models if m.get("available")]
            if avail:
                lines.append(f"- {tier}: {', '.join(avail[:3])}\n")
        return "\n".join(lines)

    async def _check_grok(self) -> str:
        lines = ["## Grok (xAI)\n"]
        if not settings.grok_api_key:
            return "## Grok\n- API key: NOT SET\n"
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
                lines.append("- Connectivity: not available\n")
        except Exception as e:
            lines.append(f"- Connectivity: FAILED — {e!s}\n")
        return "\n".join(lines)

    def _check_email_config(self) -> str:
        return (
            "## Email Config\n"
            f"- Gmail: {'set' if settings.gmail_address else 'NOT SET'}\n"
            f"- App password: {'set' if settings.gmail_app_password else 'NOT SET'}\n"
            f"- Listener: {'enabled' if getattr(settings, 'email_listener_enabled', False) else 'disabled'}\n"
        )

    def _check_telegram_config(self) -> str:
        return (
            "## Telegram Config\n"
            f"- Bot token: {'set' if settings.telegram_bot_token else 'NOT SET'}\n"
            f"- Chat ID: {'set' if settings.telegram_chat_id else 'NOT SET'}\n"
            f"- Listener: {'enabled' if getattr(settings, 'telegram_listener_enabled', False) else 'disabled'}\n"
        )

    def _check_tools(self) -> str:
        return "## Tools\n- See /api/tool-status for registered tools and usage stats.\n"

    async def _check_budget(self) -> str:
        if not self.budget:
            return "## Budget\n- Tracker not available\n"
        try:
            status = await self.budget.get_status()
            return (
                "## Budget\n"
                f"- Remaining: ${status.get('remaining', 0):.2f}\n"
                f"- Spent: ${status.get('spent', 0):.2f}\n"
                f"- Used: {status.get('percent_used', 0):.1f}%\n"
            )
        except Exception as e:
            return f"## Budget\n- Error: {e}\n"

    # ── Functional Tests ───────────────────────────────────────────────

    async def _functional_email(self) -> str:
        lines = ["## Functional: Email Round-Trip\n"]
        if not settings.gmail_address or not settings.gmail_app_password:
            return "## Functional: Email\n- SKIP: Gmail not configured\n"

        test_id = uuid.uuid4().hex[:8]
        subject = f"JARVIS Self-Test {test_id}"

        try:
            from jarvis.tools.send_email import SendEmailTool

            tool = SendEmailTool()
            t0 = time.time()
            result = await tool.execute(
                subject=subject,
                body=f"Automated self-test probe {test_id}",
                to_email=settings.gmail_address,
            )
            send_ms = int((time.time() - t0) * 1000)

            if result.success:
                lines.append(f"- Send: PASS ({send_ms}ms)\n")

                await asyncio.sleep(3)

                t1 = time.time()
                found = await self._check_email_received(subject)
                fetch_ms = int((time.time() - t1) * 1000)
                lines.append(f"- Receive: {'PASS' if found else 'NOT FOUND (may need more time)'} ({fetch_ms}ms)\n")
            else:
                lines.append(f"- Send: FAIL — {result.error}\n")
        except Exception as e:
            lines.append(f"- Error: {e}\n")
        return "\n".join(lines)

    async def _check_email_received(self, subject: str) -> bool:
        """Check IMAP for a specific subject line."""
        try:
            import imaplib

            client = imaplib.IMAP4_SSL("imap.gmail.com", 993)
            client.login(settings.gmail_address, settings.gmail_app_password)
            client.select("INBOX")
            _, data = client.search(None, "SUBJECT", f'"{subject}"')
            client.logout()
            return bool(data[0])
        except Exception:
            return False

    async def _functional_telegram(self) -> str:
        lines = ["## Functional: Telegram\n"]
        if not settings.telegram_bot_token or not settings.telegram_chat_id:
            return "## Functional: Telegram\n- SKIP: Not configured\n"

        test_id = uuid.uuid4().hex[:8]
        try:
            from jarvis.tools.send_telegram import SendTelegramTool

            tool = SendTelegramTool()
            t0 = time.time()
            result = await tool.execute(message=f"Self-test probe {test_id}")
            ms = int((time.time() - t0) * 1000)
            lines.append(f"- Send: {'PASS' if result.success else 'FAIL'} ({ms}ms)\n")
            if not result.success:
                lines.append(f"  Error: {result.error}\n")
        except Exception as e:
            lines.append(f"- Error: {e}\n")
        return "\n".join(lines)

    async def _functional_llm(self) -> str:
        lines = ["## Functional: LLM Provider Ping\n"]

        test_providers = [
            ("mistral", "mistral-small-latest", "free"),
            ("anthropic", "claude-haiku-35-20241022", "paid"),
            ("grok", "grok-3-mini", "paid"),
        ]

        providers = {}
        if self.router and hasattr(self.router, "providers"):
            providers = self.router.providers
        else:
            # Instantiate providers directly when no router available (standalone test)
            try:
                if settings.mistral_api_key:
                    from jarvis.llm.providers.mistral import MistralProvider
                    providers["mistral"] = MistralProvider()
            except Exception:
                pass
            try:
                if settings.anthropic_api_key:
                    from jarvis.llm.providers.anthropic import AnthropicProvider
                    providers["anthropic"] = AnthropicProvider()
            except Exception:
                pass
            try:
                if getattr(settings, "grok_api_key", None):
                    from jarvis.llm.providers.grok import GrokProvider
                    providers["grok"] = GrokProvider()
            except Exception:
                pass

        if not providers:
            return "## Functional: LLM\n- No providers available (no API keys configured)\n"

        for provider_name, model, cost_label in test_providers:
            if provider_name not in providers:
                lines.append(f"- {provider_name}/{model}: SKIP (not configured)\n")
                continue
            try:
                provider = providers[provider_name]
                t0 = time.time()
                resp = await provider.complete(
                    messages=[{"role": "user", "content": "Say OK"}],
                    model=model,
                    max_tokens=5,
                )
                ms = int((time.time() - t0) * 1000)
                lines.append(f"- {provider_name}/{model} [{cost_label}]: PASS ({ms}ms, {resp.total_tokens} tokens)\n")
            except Exception as e:
                lines.append(f"- {provider_name}/{model}: FAIL — {e!s}\n")
        return "\n".join(lines)

    async def _functional_memory(self) -> str:
        lines = ["## Functional: Memory\n"]

        # Vector write+search
        try:
            from jarvis.memory.models import MemoryEntry
            from jarvis.memory.vector import VectorMemory

            vector = VectorMemory(settings.data_dir)
            vector.connect()
            test_id = uuid.uuid4().hex[:8]
            content = f"self_test_probe_{test_id}"

            t0 = time.time()
            vector.add(MemoryEntry(content=content, importance_score=0.1, source="self_test"), deduplicate=False)
            write_ms = int((time.time() - t0) * 1000)

            t1 = time.time()
            results = vector.search(content, n_results=1)
            search_ms = int((time.time() - t1) * 1000)

            found = any(content in r.get("content", "") for r in results)
            lines.append(f"- Vector write: PASS ({write_ms}ms)\n")
            lines.append(f"- Vector search: {'PASS' if found else 'FAIL'} ({search_ms}ms)\n")

            if results:
                vector.delete_memory(results[0]["id"])
                lines.append("- Cleanup: PASS\n")
        except Exception as e:
            lines.append(f"- Vector: FAIL — {e}\n")

        # File write+read
        try:
            test_path = os.path.join(settings.data_dir, "test_probe.txt")
            test_content = f"probe_{uuid.uuid4().hex[:8]}"

            t0 = time.time()
            with open(test_path, "w") as f:
                f.write(test_content)
            write_ms = int((time.time() - t0) * 1000)

            t1 = time.time()
            with open(test_path) as f:
                read_content = f.read()
            read_ms = int((time.time() - t1) * 1000)

            match = read_content == test_content
            os.remove(test_path)
            lines.append(f"- File write+read: {'PASS' if match else 'FAIL'} (w:{write_ms}ms r:{read_ms}ms)\n")
        except Exception as e:
            lines.append(f"- File I/O: FAIL — {e}\n")

        return "\n".join(lines)

    async def _functional_news(self) -> str:
        lines = ["## Functional: News\n"]
        try:
            from jarvis.tools.news_monitor import NewsMonitorTool

            tool = NewsMonitorTool()
            t0 = time.time()
            result = await tool.execute(query="technology news", max_results=3)
            ms = int((time.time() - t0) * 1000)

            if result.success:
                import json

                try:
                    articles = json.loads(result.output)
                    lines.append(f"- Fetch: PASS ({ms}ms, {len(articles)} articles)\n")
                except (json.JSONDecodeError, TypeError):
                    lines.append(f"- Fetch: PASS ({ms}ms) but output not valid JSON\n")
            else:
                lines.append(f"- Fetch: FAIL — {result.error}\n")
        except Exception as e:
            lines.append(f"- News: FAIL — {e}\n")
        return "\n".join(lines)

    # ── System Health ──────────────────────────────────────────────────

    def _check_system_health(self) -> str:
        lines = ["## System Health\n"]

        # Disk usage
        for name, path in [("chroma", "chroma"), ("blob", "blob"), ("db", "jarvis.db")]:
            full_path = os.path.join(settings.data_dir, path)
            try:
                if os.path.isdir(full_path):
                    total = sum(
                        os.path.getsize(os.path.join(dp, f)) for dp, _, files in os.walk(full_path) for f in files
                    )
                elif os.path.isfile(full_path):
                    total = os.path.getsize(full_path)
                else:
                    total = 0
                mb = total / (1024 * 1024)
                lines.append(f"- {name}: {mb:.1f} MB\n")
            except Exception:
                lines.append(f"- {name}: unknown\n")

        # Vector memory stats
        try:
            from jarvis.memory.vector import VectorMemory

            v = VectorMemory(settings.data_dir)
            v.connect()
            stats = v.get_stats()
            lines.append(f"- Vector entries: {stats['total_entries']}\n")
        except Exception:
            pass

        # Skills count
        skills_dir = os.path.join(settings.data_dir, "skills")
        if os.path.isdir(skills_dir):
            count = len([f for f in os.listdir(skills_dir) if f.endswith(".md")])
            lines.append(f"- Skills: {count}\n")

        return "\n".join(lines)
