from abc import ABC, abstractmethod

from pydantic import BaseModel


class ToolResult(BaseModel):
    success: bool
    output: str
    error: str | None = None


class Tool(ABC):
    """Base class for all Jarvis tools."""

    name: str = "base_tool"
    description: str = "A tool"
    timeout_seconds: int = 30

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        pass

    def get_schema(self) -> dict:
        """Return JSON schema for the tool parameters."""
        return {
            "name": self.name,
            "description": self.description,
        }
