import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field


class MemoryEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str
    importance_score: float = 0.5
    ttl_hours: int | None = 720  # 30 days default
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    source: str = "system"
    creator_flag: bool = False
    permanent_flag: bool = False
    metadata: dict = Field(default_factory=dict)


class BlobRecord(BaseModel):
    timestamp: str
    event_type: str  # message, tool_output, llm_response, file, log
    content: str
    metadata: dict = Field(default_factory=dict)


class WorkingContext(BaseModel):
    system_prompt: str
    recent_messages: list[dict] = Field(default_factory=list)
    injected_memories: list[str] = Field(default_factory=list)
    total_tokens_estimate: int = 0
