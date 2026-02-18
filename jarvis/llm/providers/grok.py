"""
Grok/xAI LLM Provider — uses the OpenAI-compatible API at api.x.ai.
Models: grok-4-1-fast-reasoning, grok-3-mini, grok-code-fast-1, etc.
$25/month free credits + very cheap token pricing.
"""
from openai import AsyncOpenAI
from jarvis.llm.base import LLMProvider, LLMResponse
from jarvis.config import settings
from jarvis.observability.logger import get_logger

log = get_logger("llm.grok")

GROK_BASE_URL = "https://api.x.ai/v1"

GROK_MODELS = [
    "grok-4-1-fast-reasoning",
    "grok-4-1-fast-non-reasoning",
    "grok-3-mini",
    "grok-code-fast-1",
]


class GrokProvider(LLMProvider):
    name = "grok"

    def __init__(self):
        self._client = None

    def _get_client(self) -> AsyncOpenAI | None:
        if self._client is None and settings.grok_api_key:
            self._client = AsyncOpenAI(
                api_key=settings.grok_api_key,
                base_url=GROK_BASE_URL,
            )
        return self._client

    def is_available(self) -> bool:
        return bool(settings.grok_api_key)

    def get_models(self) -> list[str]:
        return list(GROK_MODELS)

    async def complete(
        self,
        messages: list[dict],
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] = None,
    ) -> LLMResponse:
        client = self._get_client()
        if not client:
            raise RuntimeError("Grok API key not configured")

        model = model or "grok-4-1-fast-reasoning"

        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            choice = response.choices[0]
            usage = response.usage

            return LLMResponse(
                content=choice.message.content or "",
                model=model,
                provider=self.name,
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
                finish_reason=choice.finish_reason,
            )
        except Exception as e:
            log.error("grok_error", error=str(e), model=model)
            raise
