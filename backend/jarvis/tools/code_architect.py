import asyncio
import json
import os

from jarvis.config import settings
from jarvis.llm.router import LLMRouter
from jarvis.observability.logger import get_logger
from jarvis.tools.base import Tool, ToolResult

log = get_logger("code_architect")


def _read_file(path: str) -> str:
    with open(path) as f:
        return f.read()


ARCHITECT_SYSTEM_PROMPT = """You are a senior software architect analyzing a codebase for a planned change.
Your job is to produce a detailed, actionable integration plan — NOT to write code.

You will receive:
1. A high-level intent describing what needs to change
2. The project's architecture documentation (skill)
3. The project's coding conventions (skill)
4. Relevant source files from the codebase

Produce a JSON plan with this structure:
{
  "summary": "One-paragraph description of the change",
  "affected_files": [
    {"path": "/app/jarvis/...", "action": "modify|create|delete", "reason": "why this file is affected"}
  ],
  "integration_points": [
    {"from": "file/module", "to": "file/module", "description": "how they connect"}
  ],
  "existing_patterns": [
    {"pattern": "description", "example_file": "path", "follow_because": "why"}
  ],
  "implementation_steps": [
    {"order": 1, "description": "what to do", "file": "path", "details": "specific changes"}
  ],
  "pitfalls": ["things to watch out for"],
  "test_strategy": ["how to verify the changes work"],
  "conventions": ["specific conventions to follow for this change"]
}

Be thorough and specific. Reference actual code patterns from the files you see.
The plan will be handed to a coding agent (Devstral) that has file editing primitives but limited reasoning.
The better your plan, the better the implementation."""


class CodeArchitectTool(Tool):
    name = "code_architect"
    description = (
        "Senior architect that analyzes the codebase and produces a detailed integration plan "
        "before code changes. Uses tier-1 model for deep reasoning. Feed the plan to coding_agent."
    )
    timeout_seconds = 120

    def __init__(self, llm_router: LLMRouter = None):
        self._router = llm_router

    def set_router(self, router: LLMRouter):
        self._router = router

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "intent": {"type": "string", "description": "High-level description of what needs to change"},
                "relevant_paths": {
                    "type": "array",
                    "description": "Optional list of file paths to read for context. Auto-discovered if omitted.",
                },
                "scope": {
                    "type": "string",
                    "description": "Scope hint: 'self_modify' (changing JARVIS code), 'workspace' (user projects), 'frontend' (dashboard)",
                },
            },
            "required": ["intent"],
        }

    async def execute(
        self, intent: str = "", relevant_paths: list[str] = None, scope: str = "self_modify", **kwargs
    ) -> ToolResult:
        if not intent:
            return ToolResult(success=False, output="", error="Missing 'intent' parameter")

        if not self._router:
            return ToolResult(success=False, output="", error="LLM router not available")

        skills_content = await self._load_skills()
        file_contents = await self._read_relevant_files(intent, relevant_paths, scope)

        user_message = f"""## Intent
{intent}

## Architecture & Conventions
{skills_content}

## Relevant Source Files
{file_contents}

Produce a detailed integration plan as JSON."""

        messages = [
            {"role": "system", "content": ARCHITECT_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        try:
            response = await self._router.complete(
                messages=messages,
                tier="level1",
                min_tier="level1",
                temperature=0.3,
                max_tokens=4096,
                task_description="code_architect_planning",
            )

            plan_text = response.content.strip()
            if plan_text.startswith("```"):
                first_nl = plan_text.find("\n")
                if first_nl > 0:
                    plan_text = plan_text[first_nl + 1 :]
                if plan_text.rstrip().endswith("```"):
                    plan_text = plan_text.rstrip()[:-3].rstrip()

            try:
                start = plan_text.find("{")
                end = plan_text.rfind("}") + 1
                if start >= 0 and end > start:
                    plan_json = json.loads(plan_text[start:end])
                else:
                    plan_json = {"raw_plan": plan_text}
            except json.JSONDecodeError:
                plan_json = {"raw_plan": plan_text}

            plan_json["_model"] = response.model
            plan_json["_provider"] = response.provider
            plan_json["_tokens"] = response.total_tokens

            return ToolResult(
                success=True,
                output=json.dumps(plan_json, indent=2),
            )
        except Exception as e:
            log.error("code_architect_failed", error=str(e))
            return ToolResult(success=False, output="", error=f"Code architect failed: {e}")

    async def _load_skills(self) -> str:
        """Load architecture and conventions skills if they exist."""
        parts = []
        skills_dir = os.path.join(settings.data_dir, "skills")
        for skill_name in ["jarvis-architecture", "jarvis-coding-conventions"]:
            path = os.path.join(skills_dir, f"{skill_name}.md")
            if os.path.exists(path):
                try:
                    content = await asyncio.get_event_loop().run_in_executor(None, lambda p=path: _read_file(p))
                    parts.append(f"### Skill: {skill_name}\n{content}\n")
                except Exception:
                    pass
        return "\n".join(parts) if parts else "(No architecture/conventions skills found yet)"

    async def _read_relevant_files(self, intent: str, paths: list[str] | None, scope: str) -> str:
        """Read relevant files for context."""
        if paths:
            file_paths = paths
        else:
            file_paths = self._discover_paths(intent, scope)

        parts = []
        total_chars = 0
        max_chars = 50000

        for fpath in file_paths:
            if total_chars >= max_chars:
                break
            try:
                if os.path.exists(fpath) and os.path.isfile(fpath):
                    content = await asyncio.get_event_loop().run_in_executor(None, lambda p=fpath: _read_file(p))
                    truncated = content[:8000]
                    parts.append(f"### {fpath}\n```\n{truncated}\n```\n")
                    total_chars += len(truncated)
            except Exception as e:
                log.warning("code_architect_file_read_error", path=fpath, error=str(e))
                continue

        return "\n".join(parts) if parts else "(No files read)"

    def _discover_paths(self, intent: str, scope: str) -> list[str]:
        """Auto-discover relevant file paths based on intent keywords."""
        base_paths = {
            "self_modify": [
                "/app/jarvis/core/loop.py",
                "/app/jarvis/core/planner.py",
                "/app/jarvis/core/executor.py",
                "/app/jarvis/tools/registry.py",
                "/app/jarvis/config.py",
                "/app/jarvis/main.py",
                "/app/jarvis/api/routes.py",
            ],
            "frontend": [
                "/frontend/src/App.tsx",
                "/frontend/src/api/client.ts",
                "/frontend/src/types/index.ts",
            ],
            "workspace": [],
        }

        paths = list(base_paths.get(scope, base_paths["self_modify"]))

        intent_lower = intent.lower()
        keyword_files = {
            "telegram": ["/app/jarvis/tools/send_telegram.py", "/app/jarvis/core/telegram_listener.py"],
            "email": ["/app/jarvis/tools/send_email.py", "/app/jarvis/core/email_listener.py"],
            "memory": ["/app/jarvis/memory/vector.py", "/app/jarvis/memory/working.py"],
            "tool": ["/app/jarvis/tools/registry.py", "/app/jarvis/tools/base.py"],
            "llm": ["/app/jarvis/llm/router.py"],
            "budget": ["/app/jarvis/budget/tracker.py"],
            "safety": ["/app/jarvis/safety/validator.py", "/app/jarvis/safety/prompt_builder.py"],
        }

        for keyword, kpaths in keyword_files.items():
            if keyword in intent_lower:
                paths.extend(kpaths)

        seen = set()
        unique = []
        for p in paths:
            if p not in seen:
                seen.add(p)
                unique.append(p)
        return unique[:15]
