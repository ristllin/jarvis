from pydantic import BaseModel


class DirectiveUpdate(BaseModel):
    directive: str


class MemoryMarkPermanent(BaseModel):
    memory_id: str


class BudgetOverride(BaseModel):
    new_cap_usd: float


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    model: str | None = None
    provider: str | None = None
    tokens_used: int | None = None
    actions_taken: list[dict] | None = None
    agentic: bool = True


class GoalsUpdate(BaseModel):
    short_term: list[str] | None = None
    mid_term: list[str] | None = None
    long_term: list[str] | None = None


class StatusResponse(BaseModel):
    status: str
    directive: str
    goals: list[str]
    short_term_goals: list[str]
    mid_term_goals: list[str]
    long_term_goals: list[str]
    short_term_memories: list[dict] = []
    active_task: str | None
    iteration: int
    is_paused: bool
    started_at: str | None


class ShortTermMemoryUpdate(BaseModel):
    add: list[str] | None = None
    remove: list[int] | None = None
    replace: list[str] | None = None


class BudgetResponse(BaseModel):
    monthly_cap: float
    spent: float
    remaining: float
    percent_used: float


class ProviderBalanceUpdate(BaseModel):
    known_balance: float | None = None
    tier: str | None = None  # paid, free, unknown
    currency: str | None = None  # USD, EUR, credits, requests, etc.
    notes: str | None = None
    reset_spending: bool = False  # Reset tracked spending when updating balance
    api_key: str | None = None  # Update the API key for this provider


class AddProviderRequest(BaseModel):
    provider: str
    api_key: str | None = None
    known_balance: float | None = None
    tier: str = "unknown"
    currency: str = "USD"  # USD, EUR, credits, requests, etc.
    notes: str | None = None
