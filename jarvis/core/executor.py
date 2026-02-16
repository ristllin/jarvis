from jarvis.tools.registry import ToolRegistry
from jarvis.memory.blob import BlobStorage
from jarvis.observability.logger import get_logger, FileLogger

log = get_logger("executor")


class Executor:
    """Executes planned actions using the tool system."""

    def __init__(self, tools: ToolRegistry, blob: BlobStorage, file_logger: FileLogger):
        self.tools = tools
        self.blob = blob
        self.file_logger = file_logger

    async def execute_plan(self, plan: dict) -> list[dict]:
        """Execute all actions in a plan and return results."""
        actions = plan.get("actions", [])
        results = []

        for i, action in enumerate(actions):
            tool_name = action.get("tool", "")
            parameters = action.get("parameters", {})

            log.info("executing_action", index=i, tool=tool_name, params=list(parameters.keys()))

            result = await self.tools.execute(tool_name, parameters)

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

            # File log
            self.file_logger.log(
                "action_executed",
                tool=tool_name,
                success=result.success,
                output_length=len(result.output) if result.output else 0,
            )

            if result.error:
                log.warning("action_error", tool=tool_name, error=result.error)

        return results
