import pytest
import pytest_asyncio
from jarvis.budget.tracker import BudgetTracker


@pytest.mark.asyncio
class TestBudgetTracker:
    @pytest_asyncio.fixture
    async def tracker(self, session_factory):
        tracker = BudgetTracker(session_factory)
        await tracker.ensure_config()
        return tracker

    async def test_initial_budget(self, tracker):
        status = await tracker.get_status()
        assert status["monthly_cap"] == 100.0
        assert status["spent"] == 0.0
        assert status["remaining"] == 100.0
        assert status["percent_used"] == 0.0

    async def test_record_usage(self, tracker):
        cost = await tracker.record_usage(
            provider="openai",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            task_description="test task",
        )
        assert cost > 0

        status = await tracker.get_status()
        assert status["spent"] > 0
        assert status["remaining"] < 100.0

    async def test_can_spend_within_budget(self, tracker):
        assert await tracker.can_spend(0.01) is True

    async def test_recommended_tier_fresh_budget(self, tracker):
        tier = await tracker.get_recommended_tier()
        assert tier == "level1"

    async def test_cost_estimation(self, tracker):
        cost = tracker._estimate_cost("openai", "gpt-4o", 1_000_000, 0)
        assert cost == 2.50

        cost = tracker._estimate_cost("ollama", "default", 1_000_000, 1_000_000)
        assert cost == 0.0

    async def test_multiple_usages_accumulate(self, tracker):
        await tracker.record_usage("openai", "gpt-4o", 1000, 500)
        await tracker.record_usage("anthropic", "claude-sonnet-4-20250514", 2000, 1000)

        status = await tracker.get_status()
        assert status["spent"] > 0
