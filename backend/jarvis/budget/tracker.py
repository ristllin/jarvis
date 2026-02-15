from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from jarvis.models import BudgetUsage, BudgetConfig
from jarvis.config import settings
from jarvis.observability.logger import get_logger

log = get_logger("budget")

# Cost per 1M tokens (approximate, updated 2026-02)
PRICING = {
    "anthropic": {
        "claude-opus-4-6": {"input": 5.0, "output": 25.0},
        "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
        "claude-haiku-35-20241022": {"input": 0.80, "output": 4.0},
    },
    "openai": {
        "gpt-5.2": {"input": 1.75, "output": 14.0},
        "gpt-4o": {"input": 2.50, "output": 10.0},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    },
    "mistral": {
        "mistral-large-latest": {"input": 2.0, "output": 6.0},
        "mistral-small-latest": {"input": 0.20, "output": 0.60},
    },
    "ollama": {
        "default": {"input": 0.0, "output": 0.0},
    },
}


class BudgetTracker:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def ensure_config(self):
        async with self.session_factory() as session:
            config = await session.get(BudgetConfig, 1)
            if not config:
                config = BudgetConfig(
                    id=1,
                    monthly_cap_usd=settings.monthly_budget_usd,
                    current_month=datetime.now(timezone.utc).strftime("%Y-%m"),
                    current_month_total=0.0,
                )
                session.add(config)
                await session.commit()

    async def record_usage(
        self, provider: str, model: str,
        input_tokens: int, output_tokens: int,
        task_description: str = None,
    ) -> float:
        cost = self._estimate_cost(provider, model, input_tokens, output_tokens)

        async with self.session_factory() as session:
            usage = BudgetUsage(
                provider=provider, model=model,
                input_tokens=input_tokens, output_tokens=output_tokens,
                cost_usd=cost, task_description=task_description,
            )
            session.add(usage)

            config = await session.get(BudgetConfig, 1)
            current_month = datetime.now(timezone.utc).strftime("%Y-%m")
            if config.current_month != current_month:
                config.current_month = current_month
                config.current_month_total = 0.0
                log.info("budget_month_reset", month=current_month)

            config.current_month_total += cost
            await session.commit()

            log.info("budget_usage",
                     provider=provider, model=model,
                     cost=round(cost, 6),
                     month_total=round(config.current_month_total, 4))
            return cost

    async def get_status(self) -> dict:
        async with self.session_factory() as session:
            config = await session.get(BudgetConfig, 1)
            if not config:
                return {"monthly_cap": settings.monthly_budget_usd, "spent": 0, "remaining": settings.monthly_budget_usd, "percent_used": 0}

            current_month = datetime.now(timezone.utc).strftime("%Y-%m")
            if config.current_month != current_month:
                spent = 0.0
            else:
                spent = config.current_month_total

            remaining = max(0, config.monthly_cap_usd - spent)
            return {
                "monthly_cap": config.monthly_cap_usd,
                "spent": round(spent, 4),
                "remaining": round(remaining, 4),
                "percent_used": round((spent / config.monthly_cap_usd) * 100, 1) if config.monthly_cap_usd > 0 else 0,
            }

    async def can_spend(self, estimated_cost: float = 0.01) -> bool:
        status = await self.get_status()
        return status["remaining"] >= estimated_cost

    async def get_recommended_tier(self) -> str:
        status = await self.get_status()
        pct = status["percent_used"]
        if pct >= 95:
            return "local_only"
        elif pct >= 80:
            return "level3"
        elif pct >= 60:
            return "level2"
        return "level1"

    def _estimate_cost(self, provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
        provider_pricing = PRICING.get(provider, {})
        model_pricing = provider_pricing.get(model, provider_pricing.get("default", {"input": 0, "output": 0}))
        input_cost = (input_tokens / 1_000_000) * model_pricing["input"]
        output_cost = (output_tokens / 1_000_000) * model_pricing["output"]
        return input_cost + output_cost
