from jarvis.tools.base import Tool, ToolResult
from jarvis.budget.tracker import BudgetTracker


class BudgetQueryTool(Tool):
    name = "budget_query"
    description = "Check remaining budget, monthly cap, spending breakdown, and recommended tier."
    timeout_seconds = 10

    def __init__(self, budget_tracker: BudgetTracker):
        self.budget = budget_tracker

    async def execute(self, **kwargs) -> ToolResult:
        try:
            status = await self.budget.get_status()
            tier = await self.budget.get_recommended_tier()
            output = (
                f"Budget Status:\n"
                f"  Monthly cap: ${status['monthly_cap']:.2f}\n"
                f"  Spent this month: ${status['spent']:.4f}\n"
                f"  Remaining: ${status['remaining']:.4f}\n"
                f"  Percent used: {status['percent_used']:.1f}%\n"
                f"  Recommended tier: {tier}\n"
            )
            return ToolResult(success=True, output=output)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {},
            "required": [],
        }
