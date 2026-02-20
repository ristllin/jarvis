import httpx
from jarvis.llm.base import LLMProvider, LLMResponse
from jarvis.config import settings
from jarvis.observability.logger import get_logger

log = get_logger("llm.ollama")


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self):
        self.base_url = settings.ollama_host

    def is_available(self) -> bool:
        try:
            resp = httpx.get(f"{self.base_url}/", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    def get_models(self) -> list[str]:
        try:
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            pass
        return ["mistral:7b-instruct"]

    async def complete(
        self,
        messages: list[dict],
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] = None,
    ) -> LLMResponse:
        model = model or "mistral:7b-instruct"

        async with httpx.AsyncClient(timeout=120) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": model,
                        "messages": messages,
                        "stream": False,
                        "options": {
                            "temperature": temperature,
                            "num_predict": max_tokens,
                        },
                    },
                )
                response.raise_for_status()
                data = response.json()

                content = data.get("message", {}).get("content", "")
                eval_count = data.get("eval_count", 0)
                prompt_count = data.get("prompt_eval_count", 0)

                return LLMResponse(
                    content=content,
                    model=model,
                    provider=self.name,
                    input_tokens=prompt_count,
                    output_tokens=eval_count,
                    total_tokens=prompt_count + eval_count,
                    finish_reason="stop",
                )
            except Exception as e:
                log.error("ollama_error", error=str(e), model=model)
                raise

    async def ensure_model(self, model: str = "mistral:7b-instruct"):
        """Pull a model if not already available."""
        available = self.get_models()
        if model in available:
            return
        log.info("ollama_pulling_model", model=model)
        async with httpx.AsyncClient(timeout=600) as client:
            try:
                await client.post(
                    f"{self.base_url}/api/pull",
                    json={"name": model, "stream": False},
                )
                log.info("ollama_model_ready", model=model)
            except Exception as e:
                log.warning("ollama_pull_failed", model=model, error=str(e))
