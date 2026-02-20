from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from jarvis.models import MetricsRecord, BudgetUsage, ToolUsageLog


class MetricsCollector:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def record(self, name: str, value: float, labels: dict = None):
        async with self.session_factory() as session:
            record = MetricsRecord(
                metric_name=name,
                metric_value=value,
                labels=labels or {},
            )
            session.add(record)
            await session.commit()

    async def get_summary(self) -> dict:
        async with self.session_factory() as session:
            tool_count = await session.scalar(select(func.count(ToolUsageLog.id)))
            tool_success = await session.scalar(
                select(func.count(ToolUsageLog.id)).where(ToolUsageLog.success.is_(True))
            )
            total_cost = await session.scalar(select(func.sum(BudgetUsage.cost_usd))) or 0.0

            return {
                "total_tool_invocations": tool_count or 0,
                "tool_success_rate": (tool_success / tool_count * 100) if tool_count else 0,
                "total_cost_usd": round(total_cost, 4),
            }
