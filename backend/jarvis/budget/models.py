from pydantic import BaseModel


class UsageRecord(BaseModel):
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    task_description: str | None = None


class BudgetSummary(BaseModel):
    monthly_cap: float
    spent: float
    remaining: float
    percent_used: float
