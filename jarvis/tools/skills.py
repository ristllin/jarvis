"""
Skills tool — JARVIS and the coding agent can read, write, list, and activate skills.

Skills are markdown files stored in /data/skills/. Each skill contains reusable
knowledge, patterns, conventions, or instructions that can be loaded into context
on demand. JARVIS can create new skills for future use and load existing ones
when working on relevant tasks.
"""
import os
import json
from datetime import datetime, timezone
from jarvis.tools.base import Tool, ToolResult
from jarvis.observability.logger import get_logger

log = get_logger("tools.skills")

SKILLS_DIR = "/data/skills"


def _ensure_skills_dir():
    os.makedirs(SKILLS_DIR, exist_ok=True)


def _skill_path(name: str) -> str:
    """Normalize skill name to a safe filename."""
    safe = name.strip().lower().replace(" ", "-").replace("/", "-")
    if not safe.endswith(".md"):
        safe += ".md"
    return os.path.join(SKILLS_DIR, safe)


def list_skills() -> list[dict]:
    """List all available skills with metadata."""
    _ensure_skills_dir()
    skills = []
    for fname in sorted(os.listdir(SKILLS_DIR)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(SKILLS_DIR, fname)
        try:
            with open(fpath, "r") as f:
                content = f.read()
            # Extract title from first # heading
            title = fname.replace(".md", "").replace("-", " ").title()
            for line in content.split("\n"):
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
            # Extract description from first non-heading paragraph
            description = ""
            in_body = False
            for line in content.split("\n"):
                if line.startswith("# "):
                    in_body = True
                    continue
                if in_body and line.strip() and not line.startswith("#"):
                    description = line.strip()[:200]
                    break
            skills.append({
                "name": fname.replace(".md", ""),
                "title": title,
                "description": description,
                "file": fname,
                "size": len(content),
                "modified": datetime.fromtimestamp(
                    os.path.getmtime(fpath), tz=timezone.utc
                ).isoformat(),
            })
        except Exception as e:
            log.warning("skill_list_error", file=fname, error=str(e))
    return skills


def read_skill(name: str) -> str | None:
    """Read a skill's full content. Returns None if not found."""
    path = _skill_path(name)
    if not os.path.isfile(path):
        # Try exact filename match
        exact = os.path.join(SKILLS_DIR, name)
        if os.path.isfile(exact):
            path = exact
        elif os.path.isfile(exact + ".md"):
            path = exact + ".md"
        else:
            return None
    with open(path, "r") as f:
        return f.read()


def write_skill(name: str, content: str) -> str:
    """Write/update a skill file. Returns the file path."""
    _ensure_skills_dir()
    path = _skill_path(name)
    with open(path, "w") as f:
        f.write(content)
    return path


class SkillsTool(Tool):
    name = "skills"
    description = (
        "Manage reusable skills — knowledge, patterns, and instructions stored as markdown files. "
        "Actions: 'list' (show available skills), 'read' (load a skill into context), "
        "'write' (create/update a skill), 'delete' (remove a skill). "
        "Skills persist across restarts and can be loaded by both you and the coding agent."
    )
    timeout_seconds = 30

    async def execute(self, action: str = "list", name: str = "",
                      content: str = "", **kwargs) -> ToolResult:
        if action == "list":
            return self._list()
        elif action == "read":
            return self._read(name)
        elif action == "write":
            return self._write(name, content)
        elif action == "delete":
            return self._delete(name)
        else:
            return ToolResult(
                success=False, output="",
                error=f"Unknown action: {action}. Use: list, read, write, delete"
            )

    def _list(self) -> ToolResult:
        skills = list_skills()
        if not skills:
            return ToolResult(
                success=True,
                output="No skills found. Create one with action='write'."
            )
        lines = [f"📚 **{len(skills)} skill(s) available:**\n"]
        for s in skills:
            lines.append(
                f"- **{s['name']}**: {s['title']}\n"
                f"  {s['description'][:100]}{'...' if len(s['description']) > 100 else ''}\n"
                f"  ({s['size']} bytes, modified {s['modified'][:10]})"
            )
        return ToolResult(success=True, output="\n".join(lines))

    def _read(self, name: str) -> ToolResult:
        if not name:
            return ToolResult(success=False, output="", error="'name' parameter required")
        content = read_skill(name)
        if content is None:
            return ToolResult(
                success=False, output="",
                error=f"Skill '{name}' not found. Use action='list' to see available skills."
            )
        return ToolResult(success=True, output=content)

    def _write(self, name: str, content: str) -> ToolResult:
        if not name:
            return ToolResult(success=False, output="", error="'name' parameter required")
        if not content:
            return ToolResult(success=False, output="", error="'content' parameter required")
        path = write_skill(name, content)
        log.info("skill_written", name=name, path=path, size=len(content))
        return ToolResult(
            success=True,
            output=f"Skill '{name}' saved to {path} ({len(content)} bytes)"
        )

    def _delete(self, name: str) -> ToolResult:
        if not name:
            return ToolResult(success=False, output="", error="'name' parameter required")
        path = _skill_path(name)
        if not os.path.isfile(path):
            return ToolResult(success=False, output="", error=f"Skill '{name}' not found")
        os.remove(path)
        log.info("skill_deleted", name=name, path=path)
        return ToolResult(success=True, output=f"Skill '{name}' deleted")

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "action": {
                    "type": "string",
                    "description": "One of: list, read, write, delete",
                    "enum": ["list", "read", "write", "delete"],
                },
                "name": {
                    "type": "string",
                    "description": "Skill name (e.g. 'python-fastapi-patterns', 'react-component-style')",
                },
                "content": {
                    "type": "string",
                    "description": "Skill content in markdown (for 'write' action). Include a # Title and description.",
                },
            },
            "required": ["action"],
        }
