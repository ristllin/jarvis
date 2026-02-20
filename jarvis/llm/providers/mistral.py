from jarvis.llm.base import LLMProvider, LLMResponse
from jarvis.config import settings
from jarvis.observability.logger import get_logger

log = get_logger("llm.mistral")

# Devstral models — specialized for agentic coding tasks
# Free on Mistral API, 256k context, 72.2% SWE-Bench Verified
DEVSTRAL_MODELS = [
    "devstral-small-2505",
    "devstral-small-2507",
    "devstral-medium-2507",
]

GENERAL_MODELS = [
    "mistral-large-latest",
    "mistral-small-latest",
]


class MistralProvider(LLMProvider):
    name = "mistral"

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None and settings.mistral_api_key:
            from mistralai import Mistral
            self._client = Mistral(api_key=settings.mistral_api_key)
        return self._client

    def is_available(self) -> bool:
        return bool(settings.mistral_api_key)

    def get_models(self) -> list[str]:
        return GENERAL_MODELS + DEVSTRAL_MODELS

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
            raise RuntimeError("Mistral API key not configured")

        model = model or "mistral-large-latest"

        try:
            response = await client.chat.complete_async(
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
            log.error("mistral_error", error=str(e), model=model)
            raise
