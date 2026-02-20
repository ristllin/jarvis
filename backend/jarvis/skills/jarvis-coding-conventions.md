# JARVIS Coding Conventions

## Language & Runtime
- Python 3.11+, async/await everywhere for I/O
- FastAPI for HTTP, aiosqlite for DB, aiohttp for outbound HTTP
- React 18 + TypeScript + TailwindCSS for frontend

## Imports
```python
# stdlib
import asyncio
import json
import os

# third-party
import aiohttp
from fastapi import APIRouter

# local
from jarvis.config import settings
from jarvis.observability.logger import get_logger
```
One blank line between groups. No wildcard imports.

## Type Hints
- All function signatures must have type hints
- Use `str | None` (not `Optional[str]`)
- Use `list[str]` (not `List[str]`)

## Logging
```python
log = get_logger("module_name")
log.info("event_name", key1=value1, key2=value2)
log.error("error_name", error=str(e))
```
Always structured key-value pairs. Never use f-strings in log messages.

## Tool Implementation
```python
from jarvis.tools.base import Tool, ToolResult

class MyTool(Tool):
    name = "my_tool"
    description = "One-line description."
    timeout_seconds = 30

    async def execute(self, param1: str = "", **kwargs) -> ToolResult:
        if not param1:
            return ToolResult(success=False, output="", error="Missing 'param1'")
        try:
            result = await do_something(param1)
            return ToolResult(success=True, output=str(result))
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "param1": {"type": "string", "description": "..."},
            },
            "required": ["param1"],
        }
```

## Error Handling
- Catch specific exceptions, not bare `except:`
- Return `ToolResult(success=False, error=...)` — never raise from tools
- Log errors with structured data before returning

## Config
- Add new settings to `config.py` Settings class
- Use env var fallback (pydantic_settings handles this)
- Default values for optional settings
- Access via `from jarvis.config import settings`

## File Paths
- `/data/` for persistent files (survives restarts)
- `/app/` for live code (ephemeral)
- `/data/code/backend/` for persistent code backup
- Always `os.makedirs(dir, exist_ok=True)` before writing

## API Routes
- Use `APIRouter(prefix="/api")`
- Pydantic models for request/response schemas
- Async handlers
- Return dicts (auto-serialized by FastAPI)

## Frontend
- Functional components with hooks
- TailwindCSS classes (no inline styles)
- API calls via `api/client.ts` (add new methods there)
- Types in `types/index.ts`

## Testing
- After code changes, validate imports: `python -c "import jarvis.module"`
- Use `self_analysis check=functional` for integration tests
- Use `coding_agent` shell primitive to run tests
