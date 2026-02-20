"""
coding_agent tool — JARVIS's main agent calls this to spawn a coding subagent
that performs complex multi-file code changes.

The main agent provides:
  - task: what to build/fix/refactor
  - system_prompt (optional): custom instructions for the subagent
  - working_directory (optional): where to focus (default: /app)
  - tier (optional): LLM tier to use (default: level2)
  - max_turns (optional): max editing iterations (default: 25)
  - skills (optional): list of skill names to load into context
  - plan_only (optional): if true, only generate a plan — don't execute
  - approved_plan (optional): previously approved plan to execute
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
        "system prompt to guide the subagent. "
        "Supports skills (reusable knowledge), planning mode, and plan execution."
    )
    timeout_seconds = 600  # 10 minutes

    def __init__(self, llm_router, blob_storage=None):
        self._agent = CodingAgent(llm_router, blob_storage)

    async def execute(
        self,
        task: str,
        system_prompt: str = None,
        working_directory: str = "/app",
        tier: str = "coding_level2",
        max_turns: int = 50,
        skills: list = None,
        plan_only: bool = False,
        approved_plan: dict = None,
        continuation_context: list = None,
        **kwargs,
    ) -> ToolResult:
        try:
            result = await self._agent.run(
                task=task,
                working_directory=working_directory,
                system_prompt=system_prompt,
                tier=tier,
                max_turns=max_turns,
                skills=skills or [],
                plan_only=plan_only,
                approved_plan=approved_plan,
                continuation_context=continuation_context,
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
                    "description": (
                        "LLM tier for the coding agent. Defaults to 'coding_level2' which uses Devstral "
                        "(free, optimized for coding). Options: 'coding_level1' (best coding model, free), "
                        "'coding_level2' (good balance, free), 'coding_level3' (lightest, free), "
                        "or standard tiers 'level1'/'level2'/'level3' for non-Devstral models."
                    ),
                },
                "max_turns": {
                    "type": "integer",
                    "description": "Maximum editing iterations (default: 50). Use higher for complex tasks.",
                },
                "skills": {
                    "type": "array",
                    "description": (
                        "List of skill names to pre-load into the subagent's context. "
                        "Use skills action=list to see available skills. "
                        "Example: ['python-fastapi-patterns', 'react-component-style']"
                    ),
                },
                "plan_only": {
                    "type": "boolean",
                    "description": (
                        "If true, the agent will explore the codebase and propose a plan, "
                        "but NOT make any changes. Use this for complex tasks where you want "
                        "to review the plan before execution."
                    ),
                },
                "approved_plan": {
                    "type": "object",
                    "description": (
                        "A previously proposed plan (from plan_only=true) that you've reviewed "
                        "and approved. The agent will execute this plan directly."
                    ),
                },
                "continuation_context": {
                    "type": "array",
                    "description": (
                        "Resume a previous coding session. Pass the 'continuation_context' "
                        "from a previous result that hit max_turns. The agent will continue "
                        "where it left off with full context of what was already done."
                    ),
                },
            },
            "required": ["task"],
        }
