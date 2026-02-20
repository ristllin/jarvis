import asyncio

from jarvis.tools.base import Tool, ToolResult


class GitTool(Tool):
    name = "git"
    description = "Run git commands in the /data/workspace directory."
    timeout_seconds = 30

    async def execute(self, command: str, **kwargs) -> ToolResult:
        # Only allow safe git commands
        allowed_prefixes = [
            "git init",
            "git clone",
            "git status",
            "git add",
            "git commit",
            "git log",
            "git diff",
            "git branch",
            "git checkout",
            "git merge",
            "git pull",
            "git push",
            "git remote",
            "git stash",
            "git tag",
            "git show",
            "git fetch",
        ]
        cmd = command.strip()
        if not any(cmd.startswith(prefix) for prefix in allowed_prefixes):
            return ToolResult(success=False, output="", error=f"Git command not allowed: {cmd}")

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd="/data/workspace",
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout_seconds)
            output = ""
            if stdout:
                output += stdout.decode("utf-8", errors="replace")
            if stderr:
                output += "\n" + stderr.decode("utf-8", errors="replace")
            return ToolResult(
                success=proc.returncode == 0,
                output=output.strip(),
                error=None if proc.returncode == 0 else f"Exit code: {proc.returncode}",
            )
        except TimeoutError:
            return ToolResult(success=False, output="", error="Git command timed out")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"command": {"type": "string", "description": "Full git command (e.g. 'git status')"}},
            "required": ["command"],
        }
