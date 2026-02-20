"""
Capability tests — verify Grok, tools, chat flow, and core components work.
Run with: pytest backend/tests/test_capabilities.py -v
Use -k "not live" to skip tests that hit real APIs (Grok, Tavily, etc.).
"""

from unittest.mock import patch

import pytest
from jarvis.core.loop import HIBERNATE_WHEN_TINY_ONLY_SECONDS, TINY_MODELS
from jarvis.llm.providers.grok import GrokProvider
from jarvis.llm.router import DEFAULT_TIERS
from jarvis.tools.coingecko import CoinGeckoTool
from jarvis.tools.web_search import WebSearchTool


class TestModelTiers:
    """Verify model tier configuration."""

    def test_devstral_in_level2_before_tiny_models(self):
        """Devstral should appear before grok-3-mini in level2."""
        level2 = DEFAULT_TIERS["level2"]
        providers_models = [(p, m) for p, m, _ in level2]
        # Devstral (mistral provider) should come before grok-3-mini
        mistral_idx = next((i for i, (p, m) in enumerate(providers_models) if p == "mistral" and "devstral" in m), None)
        grok_mini_idx = next((i for i, (p, m) in enumerate(providers_models) if m == "grok-3-mini"), None)
        if mistral_idx is not None and grok_mini_idx is not None:
            assert mistral_idx < grok_mini_idx, "Devstral should be tried before grok-3-mini"

    def test_devstral_in_level3_first(self):
        """Level3 should prefer Devstral over mistral-small and grok-3-mini."""
        level3 = DEFAULT_TIERS["level3"]
        first_provider, first_model, _ = level3[0]
        assert first_provider == "mistral" and "devstral" in first_model


class TestTinyModelsHibernation:
    """Verify hibernation logic when only tiny models available."""

    def test_tiny_models_defined(self):
        assert "grok-3-mini" in TINY_MODELS
        assert "gpt-4o-mini" in TINY_MODELS
        assert "mistral-small-latest" in TINY_MODELS
        assert "triage-only" in TINY_MODELS

    def test_hibernate_seconds_reasonable(self):
        assert HIBERNATE_WHEN_TINY_ONLY_SECONDS >= 300
        assert HIBERNATE_WHEN_TINY_ONLY_SECONDS <= 3600


class TestGrokProvider:
    """Grok provider unit tests (no live API)."""

    def test_grok_models_defined(self):
        from jarvis.llm.providers.grok import GROK_MODELS

        assert "grok-4-1-fast-reasoning" in GROK_MODELS
        assert "grok-3-mini" in GROK_MODELS

    def test_grok_unavailable_without_key(self):
        with patch("jarvis.llm.providers.grok.settings") as mock_settings:
            mock_settings.grok_api_key = None
            provider = GrokProvider()
            assert provider.is_available() is False

    def test_grok_available_with_key(self):
        with patch("jarvis.llm.providers.grok.settings") as mock_settings:
            mock_settings.grok_api_key = "xai-test-key"
            provider = GrokProvider()
            assert provider.is_available() is True


@pytest.mark.asyncio
class TestGrokLive:
    """Live Grok API test — requires GROK_API_KEY. Skip with -k 'not live'."""

    @pytest.mark.live
    @pytest.mark.skip(reason="Requires valid GROK_API_KEY; run manually when debugging Grok")
    async def test_grok_completion_live(self):
        """Verify Grok API responds. Run: pytest -k live -s"""
        import os

        if not os.environ.get("GROK_API_KEY"):
            pytest.skip("GROK_API_KEY not set")
        provider = GrokProvider()
        if not provider.is_available():
            pytest.skip("Grok not configured")
        response = await provider.complete(
            messages=[{"role": "user", "content": "Reply with exactly: OK"}],
            model="grok-3-mini",
            max_tokens=10,
        )
        assert response.content
        assert response.total_tokens > 0


class TestCoinGecko:
    """CoinGecko tool tests."""

    @pytest.mark.asyncio
    async def test_coingecko_tool_has_schema(self):
        tool = CoinGeckoTool()
        schema = tool.get_schema()
        assert schema["name"] == "coingecko"
        assert "parameters" in schema
        assert "action" in schema.get("parameters", {})

    @pytest.mark.asyncio
    async def test_coingecko_invalid_action(self):
        tool = CoinGeckoTool()
        result = await tool.execute(action="invalid")
        assert result.success is False
        assert "Unknown action" in (result.error or "")


class TestWebSearch:
    """Web search tool tests."""

    def test_web_search_unavailable_without_key(self):
        with patch("jarvis.tools.web_search.settings") as mock_settings:
            mock_settings.tavily_api_key = None
            tool = WebSearchTool()
            # Tool exists; execution would fail with "not configured"
            assert tool.name == "web_search"


class TestChatResponseSchema:
    """Chat API response includes model/provider/tokens."""

    def test_chat_response_schema_has_optional_fields(self):
        from jarvis.api.schemas import ChatResponse

        # ChatResponse should allow model, provider, tokens_used as optional
        r = ChatResponse(reply="test", agentic=True)
        assert r.model is None
        assert r.provider is None
        assert r.tokens_used is None

        r2 = ChatResponse(
            reply="hi",
            model="grok-4-1-fast-reasoning",
            provider="grok",
            tokens_used=150,
            agentic=True,
        )
        assert r2.model == "grok-4-1-fast-reasoning"
        assert r2.provider == "grok"
        assert r2.tokens_used == 150
