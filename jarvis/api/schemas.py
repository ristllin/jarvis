from pydantic import BaseModel
from typing import Optional


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
    model: Optional[str] = None
    provider: Optional[str] = None
    tokens_used: Optional[int] = None
    actions_taken: Optional[list[dict]] = None
    agentic: bool = True


class GoalsUpdate(BaseModel):
    short_term: Optional[list[str]] = None
    mid_term: Optional[list[str]] = None
    long_term: Optional[list[str]] = None


class StatusResponse(BaseModel):
    status: str
    directive: str
    goals: list[str]
    short_term_goals: list[str]
    mid_term_goals: list[str]
    long_term_goals: list[str]
    short_term_memories: list[dict] = []
    active_task: Optional[str]
    iteration: int
    is_paused: bool
    started_at: Optional[str]


class ShortTermMemoryUpdate(BaseModel):
    add: Optional[list[str]] = None
    remove: Optional[list[int]] = None
    replace: Optional[list[str]] = None


class BudgetResponse(BaseModel):
    monthly_cap: float
    spent: float
    remaining: float
    percent_used: float


class ProviderBalanceUpdate(BaseModel):
    known_balance: Optional[float] = None
    tier: Optional[str] = None       # paid, free, unknown
    currency: Optional[str] = None   # USD, EUR, credits, requests, etc.
    notes: Optional[str] = None
    reset_spending: bool = False      # Reset tracked spending when updating balance
    api_key: Optional[str] = None    # Update the API key for this provider

class AddProviderRequest(BaseModel):
    provider: str
    api_key: Optional[str] = None
    known_balance: Optional[float] = None
    tier: str = "unknown"
    currency: str = "USD"            # USD, EUR, credits, requests, etc.
    notes: Optional[str] = None
