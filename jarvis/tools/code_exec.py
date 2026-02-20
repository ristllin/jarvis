import asyncio

from jarvis.tools.base import Tool, ToolResult


class CodeExecTool(Tool):
    name = "code_exec"
    description = "Execute Python or shell code inside the Docker container. Returns stdout and stderr."
    timeout_seconds = 60

    async def execute(self, code: str, language: str = "python", **kwargs) -> ToolResult:
        try:
            if language == "python":
                proc = await asyncio.create_subprocess_exec(
                    "python",
                    "-c",
                    code,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd="/data/workspace",
                )
            elif language in ("bash", "shell", "sh"):
                proc = await asyncio.create_subprocess_exec(
                    "bash",
                    "-c",
                    code,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd="/data/workspace",
                )
            else:
                return ToolResult(success=False, output="", error=f"Unsupported language: {language}")

            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout_seconds)
            except TimeoutError:
                proc.kill()
                return ToolResult(success=False, output="", error="Execution timed out")

            output = ""
            if stdout:
                output += stdout.decode("utf-8", errors="replace")
            if stderr:
                output += "\n[STDERR]\n" + stderr.decode("utf-8", errors="replace")

            return ToolResult(
                success=proc.returncode == 0,
                output=output.strip(),
                error=None if proc.returncode == 0 else f"Exit code: {proc.returncode}",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "code": {"type": "string", "description": "Code to execute"},
                "language": {"type": "string", "description": "python or bash (default: python)"},
            },
            "required": ["code"],
        }
