"""
Coding Agent — A multi-turn LLM-powered subagent with Cursor/Claude-Code-style
editing primitives. JARVIS's main agent can spawn this to do complex code work.

The agent runs a loop:
  1. LLM sees the task + file context + available primitives
  2. LLM responds with a JSON action
  3. We execute the action and feed the result back
  4. Repeat until LLM says "done" or max turns reached
"""
import os
import re
import json
import asyncio
import subprocess
from datetime import datetime, timezone
from jarvis.observability.logger import get_logger

log = get_logger("coding_agent")

# Where JARVIS code lives
ALLOWED_ROOTS = ["/app", "/frontend", "/data"]
FORBIDDEN_PATHS = [
    "/app/jarvis/safety/rules.py",
    "/app/jarvis/observability/logger.py",
]
BACKUP_MAP = {"/app": "/data/code/backend", "/frontend": "/data/code/frontend"}

PRIMITIVES_DESCRIPTION = """You have these coding primitives. Respond with a JSON object containing "action" and its parameters.

## Available Actions

### read_file
Read a file's contents. Returns line-numbered output.
{"action": "read_file", "path": "/app/jarvis/core/loop.py"}
{"action": "read_file", "path": "/app/jarvis/core/loop.py", "offset": 50, "limit": 30}

### write_file
Create or overwrite a file entirely.
{"action": "write_file", "path": "/app/jarvis/tools/new_tool.py", "content": "...full file..."}

### str_replace
Find an exact string in a file and replace it. The old_string must match EXACTLY (whitespace included).
{"action": "str_replace", "path": "/app/jarvis/core/loop.py", "old_string": "sleep(30)", "new_string": "sleep(15)"}

### insert_after
Insert text after a specific line or string in a file.
{"action": "insert_after", "path": "/app/jarvis/main.py", "after": "app.include_router(api_router)", "content": "app.include_router(new_router)"}

### grep
Search for a pattern across files. Supports regex.
{"action": "grep", "pattern": "def execute", "path": "/app/jarvis/tools/"}
{"action": "grep", "pattern": "class.*Tool", "path": "/app", "glob": "*.py"}

### list_dir
List directory contents.
{"action": "list_dir", "path": "/app/jarvis/tools/"}

### shell
Run a shell command. Use for: running tests, installing packages, git operations, checking syntax.
{"action": "shell", "command": "cd /app && python -m pytest tests/ -x -q"}
{"action": "shell", "command": "cd /app && python -c 'import jarvis.main'"}

### delete_file
Delete a file.
{"action": "delete_file", "path": "/app/jarvis/tools/old_tool.py"}

### done
Signal that the task is complete.
{"action": "done", "summary": "Created new_tool.py with X feature, updated registry.py to register it, added tests."}

## Rules
- Use str_replace for surgical edits (preferred over write_file for existing files)
- old_string in str_replace must be EXACT — copy from read_file output
- Always read a file before editing it
- After making changes, run tests or at least validate with python -c import
- Report what you changed in the done summary
"""


class CodingAgent:
    """Multi-turn coding subagent with file editing primitives."""

    def __init__(self, llm_router, blob_storage=None):
        self.router = llm_router
        self.blob = blob_storage

    async def run(
        self,
        task: str,
        working_directory: str = "/app",
        system_prompt: str = None,
        tier: str = "level2",
        max_turns: int = 25,
        temperature: float = 0.3,
    ) -> dict:
        """Execute a coding task using multi-turn LLM + primitives loop."""

        log.info("coding_agent_start", task=task[:100], tier=tier, max_turns=max_turns)

        if self.blob:
            self.blob.store(
                event_type="coding_agent_start",
                content=f"Task: {task}",
                metadata={"tier": tier, "max_turns": max_turns, "working_directory": working_directory},
            )

        # Build system prompt
        sys_prompt = self._build_system_prompt(system_prompt, working_directory)

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": f"## Task\n{task}\n\nBegin by exploring relevant files, then make the changes needed."},
        ]

        changes_made = []
        files_read = set()
        files_modified = set()

        for turn in range(max_turns):
            try:
                response = await self.router.complete(
                    messages=messages,
                    tier=tier,
                    temperature=temperature,
                    max_tokens=4096,
                    task_description=f"coding_agent:turn_{turn}",
                )

                action = self._parse_action(response.content)
                if not action:
                    # LLM didn't return valid JSON — treat as thinking, ask to continue
                    messages.append({"role": "assistant", "content": response.content})
                    messages.append({"role": "user", "content": "Please respond with a JSON action. Use 'done' if you're finished."})
                    continue

                action_name = action.get("action", "")
                log.info("coding_agent_action", turn=turn, action=action_name)

                if action_name == "done":
                    summary = action.get("summary", "Task completed.")
                    log.info("coding_agent_done", turns=turn + 1, summary=summary[:200])
                    if self.blob:
                        self.blob.store(
                            event_type="coding_agent_done",
                            content=f"Summary: {summary}\nTurns: {turn + 1}\nFiles modified: {list(files_modified)}",
                            metadata={"turns": turn + 1, "files_modified": list(files_modified), "changes": len(changes_made)},
                        )
                    return {
                        "success": True,
                        "summary": summary,
                        "turns": turn + 1,
                        "files_modified": list(files_modified),
                        "changes": changes_made,
                    }

                # Execute the primitive
                result = await self._execute_primitive(action, working_directory)

                # Track what was done
                if action_name == "read_file":
                    files_read.add(action.get("path", ""))
                elif action_name in ("write_file", "str_replace", "insert_after"):
                    files_modified.add(action.get("path", ""))
                    changes_made.append({"action": action_name, "path": action.get("path", ""), "turn": turn})

                # Feed result back to LLM
                messages.append({"role": "assistant", "content": json.dumps(action)})
                messages.append({"role": "user", "content": f"Result:\n{result[:8000]}"})

                # Trim conversation if it gets too long (keep system + last N exchanges)
                if len(messages) > 50:
                    messages = messages[:1] + messages[-40:]

            except Exception as e:
                log.error("coding_agent_error", turn=turn, error=str(e))
                messages.append({"role": "user", "content": f"Error occurred: {str(e)}\nPlease continue or use 'done' if finished."})

        # Hit max turns
        log.warning("coding_agent_max_turns", max_turns=max_turns)
        return {
            "success": False,
            "summary": f"Hit max turns ({max_turns}). Files modified: {list(files_modified)}",
            "turns": max_turns,
            "files_modified": list(files_modified),
            "changes": changes_made,
        }

    def _build_system_prompt(self, custom_prompt: str = None, working_directory: str = "/app") -> str:
        parts = []
        parts.append("You are a coding agent — a skilled software engineer subagent of JARVIS.")
        parts.append(f"Working directory: {working_directory}")
        parts.append("")
        if custom_prompt:
            parts.append(f"## Additional Instructions\n{custom_prompt}\n")
        parts.append(PRIMITIVES_DESCRIPTION)
        parts.append("\n## Important")
        parts.append("- Respond with exactly ONE JSON action per turn.")
        parts.append("- Be precise with str_replace — copy the exact string from read_file.")
        parts.append("- After editing, validate your changes (run tests or import check).")
        parts.append("- When done, use the 'done' action with a clear summary.")
        parts.append("- You can modify files under /app, /frontend, and /data.")
        parts.append("- You CANNOT modify /app/jarvis/safety/rules.py or /app/jarvis/observability/logger.py.")
        return "\n".join(parts)

    def _parse_action(self, content: str) -> dict | None:
        """Extract a JSON action from the LLM response."""
        # Try direct JSON parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        # Try to find JSON block
        try:
            # Look for ```json ... ``` blocks
            match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', content, re.DOTALL)
            if match:
                return json.loads(match.group(1))
        except (json.JSONDecodeError, AttributeError):
            pass
        # Try to find { ... } in the content
        try:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                candidate = content[start:end]
                return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        return None

    # ── Primitive Execution ────────────────────────────────────────────────

    async def _execute_primitive(self, action: dict, working_dir: str) -> str:
        name = action.get("action", "")
        try:
            if name == "read_file":
                return self._prim_read_file(action.get("path", ""), action.get("offset"), action.get("limit"))
            elif name == "write_file":
                return self._prim_write_file(action.get("path", ""), action.get("content", ""))
            elif name == "str_replace":
                return self._prim_str_replace(action.get("path", ""), action.get("old_string", ""), action.get("new_string", ""))
            elif name == "insert_after":
                return self._prim_insert_after(action.get("path", ""), action.get("after", ""), action.get("content", ""))
            elif name == "grep":
                return await self._prim_grep(action.get("pattern", ""), action.get("path", working_dir), action.get("glob"))
            elif name == "list_dir":
                return self._prim_list_dir(action.get("path", working_dir))
            elif name == "shell":
                return await self._prim_shell(action.get("command", ""), working_dir)
            elif name == "delete_file":
                return self._prim_delete_file(action.get("path", ""))
            else:
                return f"Unknown action: {name}"
        except Exception as e:
            return f"Error executing {name}: {str(e)}"

    def _validate_path(self, path: str) -> str | None:
        real = os.path.realpath(path)
        for fp in FORBIDDEN_PATHS:
            if real == fp or real.startswith(fp + "/"):
                return f"BLOCKED: Cannot modify protected file {path}"
        if not any(real.startswith(r) for r in ALLOWED_ROOTS):
            return f"BLOCKED: Path outside allowed roots: {path}"
        return None

    def _prim_read_file(self, path: str, offset: int = None, limit: int = None) -> str:
        err = self._validate_path(path)
        if err:
            return err
        if not os.path.isfile(path):
            return f"File not found: {path}"
        with open(path, "r") as f:
            lines = f.readlines()
        total = len(lines)
        start = (offset or 1) - 1
        end = start + (limit or total)
        numbered = []
        for i, line in enumerate(lines[start:end], start=start + 1):
            numbered.append(f"{i:>5}|{line.rstrip()}")
        header = f"[{path}] ({total} lines)"
        if offset or limit:
            header += f" showing lines {start + 1}-{min(end, total)}"
        return header + "\n" + "\n".join(numbered)

    def _prim_write_file(self, path: str, content: str) -> str:
        err = self._validate_path(path)
        if err:
            return err
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        # Dual-write to backup
        self._backup_write(path, content)
        return f"Written {len(content)} bytes to {path}"

    def _prim_str_replace(self, path: str, old_string: str, new_string: str) -> str:
        err = self._validate_path(path)
        if err:
            return err
        if not os.path.isfile(path):
            return f"File not found: {path}"
        with open(path, "r") as f:
            content = f.read()
        count = content.count(old_string)
        if count == 0:
            return f"ERROR: old_string not found in {path}. Make sure it matches exactly (including whitespace)."
        if count > 1:
            return f"WARNING: old_string found {count} times in {path}. Replacing first occurrence only. Add more context to be specific."
        new_content = content.replace(old_string, new_string, 1)
        with open(path, "w") as f:
            f.write(new_content)
        self._backup_write(path, new_content)
        return f"Replaced in {path} ({count} occurrence). {len(old_string)} chars -> {len(new_string)} chars."

    def _prim_insert_after(self, path: str, after: str, content: str) -> str:
        err = self._validate_path(path)
        if err:
            return err
        if not os.path.isfile(path):
            return f"File not found: {path}"
        with open(path, "r") as f:
            file_content = f.read()
        if after not in file_content:
            return f"ERROR: anchor string not found in {path}"
        idx = file_content.index(after) + len(after)
        # Find end of line
        eol = file_content.find("\n", idx)
        if eol == -1:
            eol = len(file_content)
        new_content = file_content[:eol] + "\n" + content + file_content[eol:]
        with open(path, "w") as f:
            f.write(new_content)
        self._backup_write(path, new_content)
        return f"Inserted {len(content)} chars after '{after[:50]}...' in {path}"

    async def _prim_grep(self, pattern: str, path: str, glob_pat: str = None) -> str:
        cmd = ["grep", "-rn", "--color=never"]
        if glob_pat:
            cmd.extend(["--include", glob_pat])
        cmd.extend([pattern, path])
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
            output = stdout.decode("utf-8", errors="replace")
            if not output.strip():
                return f"No matches for '{pattern}' in {path}"
            lines = output.strip().split("\n")
            if len(lines) > 50:
                return "\n".join(lines[:50]) + f"\n... ({len(lines)} total matches, showing first 50)"
            return output.strip()
        except asyncio.TimeoutError:
            return "grep timed out"
        except Exception as e:
            return f"grep error: {e}"

    def _prim_list_dir(self, path: str) -> str:
        if not os.path.isdir(path):
            return f"Not a directory: {path}"
        entries = []
        for entry in sorted(os.listdir(path)):
            full = os.path.join(path, entry)
            if os.path.isdir(full):
                entries.append(f"  [DIR] {entry}/")
            else:
                size = os.path.getsize(full)
                entries.append(f"  {size:>8}B {entry}")
        return f"[{path}]\n" + "\n".join(entries) if entries else f"[{path}] (empty)"

    async def _prim_shell(self, command: str, working_dir: str) -> str:
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
            output = ""
            if stdout:
                output += stdout.decode("utf-8", errors="replace")
            if stderr:
                output += "\n[STDERR]\n" + stderr.decode("utf-8", errors="replace")
            status = f"[exit code: {proc.returncode}]"
            result = f"{status}\n{output.strip()}"
            if len(result) > 8000:
                result = result[:8000] + "\n[...truncated...]"
            return result
        except asyncio.TimeoutError:
            return "Command timed out (60s)"
        except Exception as e:
            return f"Shell error: {e}"

    def _prim_delete_file(self, path: str) -> str:
        err = self._validate_path(path)
        if err:
            return err
        if not os.path.isfile(path):
            return f"File not found: {path}"
        os.remove(path)
        return f"Deleted {path}"

    def _backup_write(self, path: str, content: str):
        """Dual-write to persistent backup in /data/code/."""
        for live_root, backup_root in BACKUP_MAP.items():
            if path.startswith(live_root):
                backup_path = path.replace(live_root, backup_root, 1)
                try:
                    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                    with open(backup_path, "w") as f:
                        f.write(content)
                except Exception:
                    pass
                return
