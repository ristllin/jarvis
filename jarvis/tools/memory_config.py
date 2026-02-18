"""Tool for JARVIS to view and update its own memory settings."""
from jarvis.tools.base import Tool, ToolResult
from jarvis.memory.working import WorkingMemory
from jarvis.observability.logger import get_logger

log = get_logger("tool.memory_config")

RANGES = {
    "retrieval_count": (1, 100),
    "relevance_threshold": (0.0, 1.0),
    "decay_factor": (0.5, 1.0),
    "max_context_tokens": (10_000, 200_000),
}


class MemoryConfigTool(Tool):
    name = "memory_config"
    description = (
        "View or update your memory settings. Use this to tune how many memories you retrieve, "
        "how relevant they must be, how fast old memories decay, and your context window size. "
        "Action: 'view' to see current settings, 'update' to change them."
    )
    timeout_seconds = 5

    def __init__(self, working: WorkingMemory):
        self.working = working

    async def execute(
        self,
        action: str = "view",
        retrieval_count: int = None,
        relevance_threshold: float = None,
        decay_factor: float = None,
        max_context_tokens: int = None,
        **kwargs,
    ) -> ToolResult:
        try:
            if action == "view":
                cfg = self.working.memory_config
                lines = [
                    "Current memory settings:",
                    f"  retrieval_count: {cfg.get('retrieval_count', 10)} (memories per iteration, 1-100)",
                    f"  relevance_threshold: {cfg.get('relevance_threshold', 0.0)} (0-1, min similarity to include)",
                    f"  decay_factor: {cfg.get('decay_factor', 0.95)} (0.5-1, how fast old memories decay)",
                    f"  max_context_tokens: {cfg.get('max_context_tokens', 120000)} (context window size)",
                ]
                return ToolResult(success=True, output="\n".join(lines))

            elif action == "update":
                updates = {}
                if retrieval_count is not None:
                    lo, hi = RANGES["retrieval_count"]
                    updates["retrieval_count"] = max(lo, min(hi, int(retrieval_count)))
                if relevance_threshold is not None:
                    lo, hi = RANGES["relevance_threshold"]
                    updates["relevance_threshold"] = max(lo, min(hi, float(relevance_threshold)))
                if decay_factor is not None:
                    lo, hi = RANGES["decay_factor"]
                    updates["decay_factor"] = max(lo, min(hi, float(decay_factor)))
                if max_context_tokens is not None:
                    lo, hi = RANGES["max_context_tokens"]
                    updates["max_context_tokens"] = max(lo, min(hi, int(max_context_tokens)))

                if not updates:
                    return ToolResult(
                        success=False,
                        output="",
                        error="No valid parameters. Provide retrieval_count, relevance_threshold, decay_factor, or max_context_tokens.",
                    )

                for k, v in updates.items():
                    self.working.update_config(**{k: v})

                log.info("memory_config_tool_updated", updates=updates)
                return ToolResult(
                    success=True,
                    output=f"Updated: {updates}. Current config: {dict(self.working.memory_config)}",
                )

            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unknown action: {action}. Use 'view' or 'update'.",
                )

        except Exception as e:
            log.error("memory_config_tool_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "action": {
                    "type": "string",
                    "description": "'view' to see current settings, 'update' to change them",
                },
                "retrieval_count": {
                    "type": "integer",
                    "description": "Memories to retrieve per iteration (1-100). For update action.",
                },
                "relevance_threshold": {
                    "type": "number",
                    "description": "Min similarity 0-1 to include a memory. 0=all. For update action.",
                },
                "decay_factor": {
                    "type": "number",
                    "description": "Importance decay per cycle (0.5-1). Lower=faster decay. For update action.",
                },
                "max_context_tokens": {
                    "type": "integer",
                    "description": "Max context window size (10000-200000). For update action.",
                },
            },
            "required": ["action"],
        }
