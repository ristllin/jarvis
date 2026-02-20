from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from jarvis.observability.logger import get_logger
from jarvis.tools.base import Tool

if TYPE_CHECKING:
    from jarvis.tools.registry import ToolRegistry

log = get_logger("monitor_tool")

# Tools that can be safely probed with a dry-run style check
_SAFE_PROBE_TOOLS = frozenset(
    {
        "web_search",
        "web_browse",
        "budget_query",
        "self_analysis",
        "memory_search",
        "coingecko",
        "news_monitor",
    }
)


class MonitorTool(Tool):
    name = "monitor_tool"
    description = "Monitors health of registered tools."

    def __init__(self, registry: ToolRegistry, check_interval: int = 300):
        self.registry = registry
        self.check_interval = check_interval

    async def execute(self, **kwargs) -> None:
        pass

    async def check_tools(self):
        await asyncio.sleep(30)
        while True:
            healthy = 0
            total = 0
            for tool_name, tool in self.registry.tools.items():
                total += 1
                try:
                    schema = tool.get_schema()
                    has_name = bool(schema.get("name"))
                    has_desc = bool(schema.get("description"))
                    if has_name and has_desc:
                        healthy += 1
                    else:
                        log.warning("tool_schema_incomplete", tool=tool_name, has_name=has_name, has_desc=has_desc)
                except Exception as e:
                    log.error("tool_health_check_failed", tool=tool_name, error=str(e))

            log.info("tool_health_summary", healthy=healthy, total=total)
            await asyncio.sleep(self.check_interval)

    def start_monitoring(self):
        asyncio.create_task(self.check_tools())
