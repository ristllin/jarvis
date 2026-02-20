from jarvis.config import settings
from jarvis.llm.base import LLMProvider, LLMResponse
from jarvis.observability.logger import get_logger

log = get_logger("llm.openai")


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None and settings.openai_api_key:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._client

    def is_available(self) -> bool:
        return bool(settings.openai_api_key)

    def get_models(self) -> list[str]:
        return ["gpt-5.2", "gpt-4o", "gpt-4o-mini"]

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
            raise RuntimeError("OpenAI API key not configured")

        model = model or "gpt-4o"

        # GPT-5.x models use max_completion_tokens instead of max_tokens
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if model.startswith("gpt-5"):
            kwargs["max_completion_tokens"] = max_tokens
        else:
            kwargs["max_tokens"] = max_tokens

        try:
            response = await client.chat.completions.create(**kwargs)
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
            log.error("openai_error", error=str(e), model=model)
            raise
