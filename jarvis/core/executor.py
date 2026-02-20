import time

from jarvis.memory.blob import BlobStorage
from jarvis.observability.logger import FileLogger, get_logger
from jarvis.tools.registry import ToolRegistry

log = get_logger("executor")


class Executor:
    """Executes planned actions using the tool system."""

    def __init__(self, tools: ToolRegistry, blob: BlobStorage, file_logger: FileLogger, session_factory=None):
        self.tools = tools
        self.blob = blob
        self.file_logger = file_logger
        self.session_factory = session_factory

    async def execute_plan(self, plan: dict) -> list[dict]:
        """Execute all actions in a plan and return results.

        Each action may include a 'tier' field assigned by the planner,
        which is passed through to tools that internally use LLM routing.
        """
        actions = plan.get("actions", [])
        results = []

        for i, action in enumerate(actions):
            tool_name = action.get("tool", "")
            parameters = action.get("parameters", {})
            action_tier = action.get("tier")

            if action_tier and "tier" not in parameters:
                parameters["tier"] = action_tier

            log.info("executing_action", index=i, tool=tool_name, tier=action_tier, params=list(parameters.keys()))

            t0 = time.monotonic()
            result = await self.tools.execute(tool_name, parameters)
            duration_ms = int((time.monotonic() - t0) * 1000)

            result_record = {
                "action_index": i,
                "tool": tool_name,
                "parameters": parameters,
                "success": result.success,
                "output": result.output[:2000] if result.output else "",
                "error": result.error,
            }
            results.append(result_record)

            # Store in blob
            self.blob.store(
                event_type="tool_output",
                content=f"Tool: {tool_name}\nSuccess: {result.success}\nOutput: {result.output[:1000]}",
                metadata={"tool": tool_name, "success": result.success},
            )

            # Log to ToolUsageLog DB table for analytics
            await self._log_tool_usage(
                tool_name,
                parameters,
                result.success,
                result.output[:500] if result.output else "",
                result.error,
                duration_ms,
            )

            # File log
            self.file_logger.log(
                "action_executed",
                tool=tool_name,
                success=result.success,
                output_length=len(result.output) if result.output else 0,
                duration_ms=duration_ms,
            )

            if result.error:
                log.warning("action_error", tool=tool_name, error=result.error)

        return results

    async def _log_tool_usage(
        self, tool_name: str, parameters: dict, success: bool, summary: str, error: str | None, duration_ms: int
    ):
        """Persist tool usage to DB for analytics."""
        if not self.session_factory:
            return
        try:
            from jarvis.models import ToolUsageLog

            async with self.session_factory() as session:
                entry = ToolUsageLog(
                    tool_name=tool_name,
                    parameters={k: str(v)[:200] for k, v in (parameters or {}).items()},
                    result_summary=summary[:500] if summary else None,
                    success=success,
                    duration_ms=duration_ms,
                    error=error[:500] if error else None,
                )
                session.add(entry)
                await session.commit()
        except Exception as e:
            log.warning("tool_usage_log_failed", error=str(e))
