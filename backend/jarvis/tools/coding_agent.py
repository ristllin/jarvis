"""
coding_agent tool — JARVIS's main agent calls this to spawn a coding subagent
that performs complex multi-file code changes.

The main agent provides:
  - task: what to build/fix/refactor
  - system_prompt (optional): custom instructions for the subagent
  - working_directory (optional): where to focus (default: /app)
  - tier (optional): LLM tier to use (default: level2)
  - max_turns (optional): max editing iterations (default: 25)
"""

import json

from jarvis.agents.coding import CodingAgent
from jarvis.observability.logger import get_logger
from jarvis.tools.base import Tool, ToolResult

log = get_logger("tools.coding_agent")


class CodingAgentTool(Tool):
    name = "coding_agent"
    description = (
        "Spawn a coding subagent to perform complex code changes. "
        "The subagent has read, write, str_replace, grep, shell, and other "
        "editing primitives — like a full coding IDE. Use this for multi-file "
        "edits, building new features, refactoring, writing tests, or modifying "
        "JARVIS's own code. You configure the task and optionally a custom "
        "system prompt to guide the subagent."
    )
    timeout_seconds = 600  # 10 minutes — complex tasks take time

    def __init__(self, llm_router, blob_storage=None):
        self._agent = CodingAgent(llm_router, blob_storage)

    async def execute(
        self,
        task: str,
        system_prompt: str = None,
        working_directory: str = "/app",
        tier: str = "level2",
        max_turns: int = 25,
        **kwargs,
    ) -> ToolResult:
        try:
            result = await self._agent.run(
                task=task,
                working_directory=working_directory,
                system_prompt=system_prompt,
                tier=tier,
                max_turns=max_turns,
            )

            output = json.dumps(result, indent=2)
            return ToolResult(
                success=result.get("success", False),
                output=output,
                error=None if result.get("success") else result.get("summary", "Coding agent failed"),
            )
        except Exception as e:
            log.error("coding_agent_tool_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "task": {
                    "type": "string",
                    "description": (
                        "Detailed description of what to build/change/fix. "
                        "Be specific about which files, what behavior, and any constraints."
                    ),
                },
                "system_prompt": {
                    "type": "string",
                    "description": (
                        "Optional custom system prompt for the subagent. Use to add context, "
                        "coding style preferences, architecture constraints, etc."
                    ),
                },
                "working_directory": {
                    "type": "string",
                    "description": "Root directory for the work (default: /app for backend, /frontend for UI)",
                },
                "tier": {
                    "type": "string",
                    "description": "LLM tier: level1 (strongest), level2 (default, good balance), level3 (cheapest)",
                },
                "max_turns": {
                    "type": "integer",
                    "description": "Maximum editing iterations (default: 25)",
                },
            },
            "required": ["task"],
        }
