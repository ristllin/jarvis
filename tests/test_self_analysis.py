"""Tests for the self_analysis tool — validates self-assessment capability."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from jarvis.tools.self_analysis import SelfAnalysisTool


@pytest.fixture
def mock_router():
    router = MagicMock()
    router.get_available_providers.return_value = ["mistral", "grok", "ollama"]
    router.providers = {
        "mistral": MagicMock(is_available=MagicMock(return_value=True)),
        "grok": MagicMock(is_available=MagicMock(return_value=True)),
        "ollama": MagicMock(is_available=MagicMock(return_value=True)),
    }
    return router


@pytest.fixture
def mock_budget():
    budget = MagicMock()
    budget.get_status = AsyncMock(return_value={"monthly_cap": 100, "spent": 10, "remaining": 90, "percent_used": 10})
    return budget


class TestSelfAnalysisTool:
    def test_schema(self):
        tool = SelfAnalysisTool(llm_router=MagicMock(), budget_tracker=MagicMock())
        schema = tool.get_schema()
        assert schema["name"] == "self_analysis"
        assert "check" in schema.get("parameters", {})

    @pytest.mark.asyncio
    async def test_check_providers(self, mock_router, mock_budget):
        tool = SelfAnalysisTool(llm_router=mock_router, budget_tracker=mock_budget)
        result = await tool.execute(check="providers")
        assert result.success
        assert "mistral" in result.output

    @pytest.mark.asyncio
    async def test_check_budget(self, mock_router, mock_budget):
        tool = SelfAnalysisTool(llm_router=mock_router, budget_tracker=mock_budget)
        result = await tool.execute(check="budget")
        assert result.success
        assert "90" in result.output or "remaining" in result.output.lower()

    @pytest.mark.asyncio
    async def test_check_all(self, mock_router, mock_budget):
        tool = SelfAnalysisTool(llm_router=mock_router, budget_tracker=mock_budget)
        result = await tool.execute(check="all")
        assert result.success
