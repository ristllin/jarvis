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
    active_task: Optional[str]
    iteration: int
    is_paused: bool
    started_at: Optional[str]


class BudgetResponse(BaseModel):
    monthly_cap: float
    spent: float
    remaining: float
    percent_used: float
