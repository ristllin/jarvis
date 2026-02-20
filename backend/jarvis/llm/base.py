from abc import ABC, abstractmethod

from pydantic import BaseModel


class LLMResponse(BaseModel):
    content: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    finish_reason: str | None = None
    raw_response: dict | None = None


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    name: str = "base"

    @abstractmethod
    async def complete(
        self,
        messages: list[dict],
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] = None,
    ) -> LLMResponse:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def get_models(self) -> list[str]:
        pass
