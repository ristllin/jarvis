import datetime
from sqlalchemy import Column, String, Float, Integer, DateTime, Text, Boolean, JSON, func
from jarvis.database import Base


class JarvisState(Base):
    __tablename__ = "jarvis_state"

    id = Column(Integer, primary_key=True, default=1)
    directive = Column(Text, nullable=False)
    current_goals = Column(JSON, default=list)  # kept for compat
    short_term_goals = Column(JSON, default=list)
    mid_term_goals = Column(JSON, default=list)
    long_term_goals = Column(JSON, default=list)
    active_task = Column(Text, nullable=True)
    loop_iteration = Column(Integer, default=0)
    is_paused = Column(Boolean, default=False)
    last_heartbeat = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    role = Column(String(20), nullable=False)  # "creator" or "jarvis"
    content = Column(Text, nullable=False)
    metadata_ = Column("metadata", JSON, default=dict)


class BudgetUsage(Base):
    __tablename__ = "budget_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    provider = Column(String(50), nullable=False)
    model = Column(String(100), nullable=False)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    task_description = Column(Text, nullable=True)


class BudgetConfig(Base):
    __tablename__ = "budget_config"

    id = Column(Integer, primary_key=True, default=1)
    monthly_cap_usd = Column(Float, nullable=False, default=100.0)
    current_month = Column(String(7), nullable=False)  # YYYY-MM
    current_month_total = Column(Float, default=0.0)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class LLMProviderConfig(Base):
    __tablename__ = "llm_provider_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider_name = Column(String(50), unique=True, nullable=False)
    api_key_encrypted = Column(Text, nullable=True)
    is_enabled = Column(Boolean, default=True)
    priority = Column(Integer, default=10)
    models_config = Column(JSON, default=dict)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ToolUsageLog(Base):
    __tablename__ = "tool_usage_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    tool_name = Column(String(100), nullable=False)
    parameters = Column(JSON, nullable=True)
    result_summary = Column(Text, nullable=True)
    success = Column(Boolean, default=True)
    duration_ms = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)


class MetricsRecord(Base):
    __tablename__ = "metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    metric_name = Column(String(100), nullable=False)
    metric_value = Column(Float, nullable=False)
    labels = Column(JSON, default=dict)
