from jarvis.config import settings
from jarvis.llm.base import LLMProvider, LLMResponse
from jarvis.observability.logger import get_logger

log = get_logger("llm.anthropic")


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None and settings.anthropic_api_key:
            import anthropic

            self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        return self._client

    def is_available(self) -> bool:
        return bool(settings.anthropic_api_key)

    def get_models(self) -> list[str]:
        return ["claude-opus-4-6", "claude-sonnet-4-20250514", "claude-haiku-35-20241022"]

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
            raise RuntimeError("Anthropic API key not configured")

        model = model or "claude-sonnet-4-20250514"

        # Extract system message
        system_msg = ""
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                chat_messages.append(msg)

        if not chat_messages:
            chat_messages = [{"role": "user", "content": "Begin your next iteration."}]

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": chat_messages,
        }
        if system_msg:
            kwargs["system"] = system_msg

        try:
            response = await client.messages.create(**kwargs)
            content = ""
            for block in response.content:
                if hasattr(block, "text"):
                    content += block.text

            return LLMResponse(
                content=content,
                model=model,
                provider=self.name,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                total_tokens=response.usage.input_tokens + response.usage.output_tokens,
                finish_reason=response.stop_reason,
            )
        except Exception as e:
            log.error("anthropic_error", error=str(e), model=model)
            raise
