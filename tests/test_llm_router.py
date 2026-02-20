from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from jarvis.budget.tracker import BudgetTracker
from jarvis.llm.base import LLMResponse
from jarvis.llm.router import DEFAULT_TIERS, LLMRouter


@pytest.mark.asyncio
class TestLLMRouter:
    @pytest_asyncio.fixture
    async def budget(self, session_factory):
        tracker = BudgetTracker(session_factory)
        await tracker.ensure_config()
        return tracker

    def test_default_tiers_defined(self):
        assert "level1" in DEFAULT_TIERS
        assert "level2" in DEFAULT_TIERS
        assert "level3" in DEFAULT_TIERS
        assert "local_only" in DEFAULT_TIERS

    def test_tier_info(self, budget):
        router = LLMRouter(budget)
        info = router.get_tier_info()
        assert "level1" in info
        for models in info.values():
            for m in models:
                assert "provider" in m
                assert "model" in m
                assert "cost" in m
                assert "available" in m

    def test_available_providers(self, budget):
        router = LLMRouter(budget)
        providers = router.get_available_providers()
        assert isinstance(providers, list)

    async def test_complete_with_mock_provider(self, budget):
        router = LLMRouter(budget)

        mock_response = LLMResponse(
            content='{"thinking": "test", "actions": []}',
            model="test-model",
            provider="test",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
        )

        mock_provider = MagicMock()
        mock_provider.name = "test"
        mock_provider.is_available.return_value = True
        mock_provider.complete = AsyncMock(return_value=mock_response)

        router.providers["test"] = mock_provider
        router.tiers["level1"] = [("test", "test-model", "free")]

        response = await router.complete(
            messages=[{"role": "user", "content": "test"}],
            tier="level1",
        )
        assert response.content == '{"thinking": "test", "actions": []}'
        assert response.provider == "test"

    async def test_fallback_on_provider_failure(self, budget):
        router = LLMRouter(budget)

        failing_provider = MagicMock()
        failing_provider.name = "failing"
        failing_provider.is_available.return_value = True
        failing_provider.complete = AsyncMock(side_effect=RuntimeError("API down"))

        success_response = LLMResponse(
            content="fallback response",
            model="fallback-model",
            provider="fallback",
            input_tokens=50,
            output_tokens=25,
            total_tokens=75,
        )
        fallback_provider = MagicMock()
        fallback_provider.name = "fallback"
        fallback_provider.is_available.return_value = True
        fallback_provider.complete = AsyncMock(return_value=success_response)

        router.providers = {"failing": failing_provider, "fallback": fallback_provider}
        router.tiers["level1"] = [("failing", "fail-model", "free"), ("fallback", "fallback-model", "free")]
        router.tiers["level2"] = []
        router.tiers["level3"] = []
        router.tiers["local_only"] = []

        response = await router.complete(
            messages=[{"role": "user", "content": "test"}],
            tier="level1",
        )
        assert response.content == "fallback response"
        assert response.provider == "fallback"
