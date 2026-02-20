import os
from jarvis.tools.base import Tool, ToolResult


ALLOWED_BASE = "/data"


class FileReadTool(Tool):
    name = "file_read"
    description = "Read a file from the /data directory."
    timeout_seconds = 10

    async def execute(self, path: str, **kwargs) -> ToolResult:
        full_path = os.path.realpath(os.path.join(ALLOWED_BASE, path.lstrip("/")))
        if not full_path.startswith(ALLOWED_BASE):
            return ToolResult(success=False, output="", error="Path outside allowed directory")
        try:
            with open(full_path, "r") as f:
                content = f.read()
            if len(content) > 50000:
                content = content[:50000] + "\n\n[...truncated...]"
            return ToolResult(success=True, output=content)
        except FileNotFoundError:
            return ToolResult(success=False, output="", error=f"File not found: {path}")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"path": {"type": "string", "description": "File path relative to /data"}},
            "required": ["path"],
        }


class FileWriteTool(Tool):
    name = "file_write"
    description = "Write content to a file in the /data directory."
    timeout_seconds = 10

    async def execute(self, path: str, content: str, **kwargs) -> ToolResult:
        full_path = os.path.realpath(os.path.join(ALLOWED_BASE, path.lstrip("/")))
        if not full_path.startswith(ALLOWED_BASE):
            return ToolResult(success=False, output="", error="Path outside allowed directory")
        try:
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w") as f:
                f.write(content)
            return ToolResult(success=True, output=f"Written {len(content)} bytes to {path}")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "path": {"type": "string", "description": "File path relative to /data"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        }


class FileListTool(Tool):
    name = "file_list"
    description = "List files in a directory under /data."
    timeout_seconds = 10

    async def execute(self, path: str = "", **kwargs) -> ToolResult:
        full_path = os.path.realpath(os.path.join(ALLOWED_BASE, path.lstrip("/")))
        if not full_path.startswith(ALLOWED_BASE):
            return ToolResult(success=False, output="", error="Path outside allowed directory")
        try:
            entries = []
            for entry in os.listdir(full_path):
                entry_path = os.path.join(full_path, entry)
                is_dir = os.path.isdir(entry_path)
                size = os.path.getsize(entry_path) if not is_dir else 0
                entries.append(f"{'[DIR]' if is_dir else f'{size}B':>10} {entry}")
            return ToolResult(success=True, output="\n".join(entries) if entries else "(empty directory)")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"path": {"type": "string", "description": "Directory path relative to /data"}},
            "required": [],
        }
