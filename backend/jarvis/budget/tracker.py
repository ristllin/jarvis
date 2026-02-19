from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from jarvis.models import BudgetUsage, BudgetConfig, ProviderBalance
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
        # Mistral free tier — no dollar cost to us (usage-limited, not pay-per-token)
        "mistral-large-latest": {"input": 0.0, "output": 0.0},
        "mistral-small-latest": {"input": 0.0, "output": 0.0},
        # Devstral coding models — also free on Mistral API
        "devstral-small-2505": {"input": 0.0, "output": 0.0},
        "devstral-small-2507": {"input": 0.0, "output": 0.0},
        "devstral-medium-2507": {"input": 0.0, "output": 0.0},
    },
    "grok": {
        "grok-4-1-fast-reasoning": {"input": 0.20, "output": 0.50},
        "grok-4-1-fast-non-reasoning": {"input": 0.20, "output": 0.50},
        "grok-3-mini": {"input": 0.30, "output": 0.50},
        "grok-code-fast-1": {"input": 0.20, "output": 1.50},
    },
    "ollama": {
        "default": {"input": 0.0, "output": 0.0},
    },
    "tavily": {
        "default": {"input": 0.0, "output": 0.0},  # per-request pricing, tracked separately
    },
}

# Currency symbols for display
CURRENCY_SYMBOLS = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "credits": "",    # show as "989 credits"
    "requests": "",   # show as "989 requests"
}

# Default known balances — seeded on first run, then updated by user/JARVIS
DEFAULT_PROVIDERS = [
    {"provider": "anthropic",  "known_balance": 11.71, "tier": "paid",    "currency": "USD",     "notes": "Prepaid credits"},
    {"provider": "openai",     "known_balance": 18.85, "tier": "paid",    "currency": "USD",     "notes": "Prepaid credits"},
    {"provider": "mistral",    "known_balance": None,  "tier": "free",    "currency": "USD",     "notes": "Free tier — limits unknown"},
    {"provider": "grok",       "known_balance": 25.0,  "tier": "paid",    "currency": "USD",     "notes": "xAI — $25/month free credits"},
    {"provider": "tavily",     "known_balance": 1000,  "tier": "free",    "currency": "credits", "notes": "Monthly plan — 1000 credits/month"},
    {"provider": "ollama",     "known_balance": None,  "tier": "free",    "currency": "USD",     "notes": "Local — no cost"},
]


class BudgetTracker:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def ensure_config(self):
        """Ensure budget config and provider balances exist."""
        async with self.session_factory() as session:
            # Budget config
            config = await session.get(BudgetConfig, 1)
            if not config:
                config = BudgetConfig(
                    id=1,
                    monthly_cap_usd=settings.monthly_budget_usd,
                    current_month=datetime.now(timezone.utc).strftime("%Y-%m"),
                    current_month_total=0.0,
                )
                session.add(config)

            # Seed provider balances if empty
            result = await session.execute(select(func.count()).select_from(ProviderBalance))
            count = result.scalar()
            if count == 0:
                for p in DEFAULT_PROVIDERS:
                    bal = ProviderBalance(
                        provider=p["provider"],
                        known_balance=p["known_balance"],
                        tier=p["tier"],
                        currency=p.get("currency", "USD"),
                        notes=p["notes"],
                        spent_tracked=0.0,
                        balance_updated_at=datetime.now(timezone.utc) if p["known_balance"] is not None else None,
                    )
                    session.add(bal)
                log.info("provider_balances_seeded", count=len(DEFAULT_PROVIDERS))
            else:
                # Migrate: add any new providers from DEFAULT_PROVIDERS that don't exist yet
                for p in DEFAULT_PROVIDERS:
                    result = await session.execute(
                        select(ProviderBalance).where(ProviderBalance.provider == p["provider"])
                    )
                    existing = result.scalar_one_or_none()
                    if not existing:
                        bal = ProviderBalance(
                            provider=p["provider"],
                            known_balance=p["known_balance"],
                            tier=p["tier"],
                            currency=p.get("currency", "USD"),
                            notes=p["notes"],
                            spent_tracked=0.0,
                            balance_updated_at=datetime.now(timezone.utc) if p["known_balance"] is not None else None,
                        )
                        session.add(bal)
                        log.info("provider_added_migration", provider=p["provider"])
                    elif existing:
                        # Update currency if needed
                        if p.get("currency") and p["currency"] != "USD" and (not existing.currency or existing.currency == "USD"):
                            existing.currency = p["currency"]
                            if existing.known_balance is None and p["known_balance"] is not None:
                                existing.known_balance = p["known_balance"]
                                existing.balance_updated_at = datetime.now(timezone.utc)
                            if p.get("notes"):
                                existing.notes = p["notes"]
                            log.info("provider_currency_migrated", provider=p["provider"], currency=p["currency"])

            await session.commit()

    async def record_usage(
        self, provider: str, model: str,
        input_tokens: int, output_tokens: int,
        task_description: str = None,
    ) -> float:
        cost = self._estimate_cost(provider, model, input_tokens, output_tokens)

        async with self.session_factory() as session:
            # Record in usage log
            usage = BudgetUsage(
                provider=provider, model=model,
                input_tokens=input_tokens, output_tokens=output_tokens,
                cost_usd=cost, task_description=task_description,
            )
            session.add(usage)

            # Update monthly total
            config = await session.get(BudgetConfig, 1)
            current_month = datetime.now(timezone.utc).strftime("%Y-%m")
            if config.current_month != current_month:
                config.current_month = current_month
                config.current_month_total = 0.0
                log.info("budget_month_reset", month=current_month)

            config.current_month_total += cost

            # Update per-provider spending
            result = await session.execute(
                select(ProviderBalance).where(ProviderBalance.provider == provider)
            )
            pbal = result.scalar_one_or_none()
            if pbal:
                # For non-USD providers (credits, requests), track 1 unit per call
                # For USD providers, track the dollar cost
                if pbal.currency and pbal.currency not in ("USD", "EUR", "GBP"):
                    pbal.spent_tracked += 1  # 1 credit/request per API call
                else:
                    pbal.spent_tracked += cost
            else:
                # Auto-create balance entry for new providers
                pbal = ProviderBalance(
                    provider=provider,
                    known_balance=None,
                    tier="unknown",
                    currency="USD",
                    spent_tracked=cost,
                    notes="Auto-created from usage",
                )
                session.add(pbal)

            await session.commit()

            log.info("budget_usage",
                     provider=provider, model=model,
                     cost=round(cost, 6),
                     month_total=round(config.current_month_total, 4))
            return cost

    async def get_status(self) -> dict:
        """Get overall budget status + per-provider breakdown."""
        async with self.session_factory() as session:
            config = await session.get(BudgetConfig, 1)
            if not config:
                return {
                    "monthly_cap": settings.monthly_budget_usd,
                    "spent": 0, "remaining": settings.monthly_budget_usd,
                    "percent_used": 0, "source": "config", "providers": [],
                }

            current_month = datetime.now(timezone.utc).strftime("%Y-%m")
            if config.current_month != current_month:
                spent = 0.0
            else:
                spent = config.current_month_total

            # Get provider balances
            result = await session.execute(select(ProviderBalance).order_by(ProviderBalance.provider))
            provider_balances = result.scalars().all()

            providers = []
            total_available = 0.0
            for pb in provider_balances:
                currency = pb.currency or "USD"
                estimated_remaining = None
                if pb.known_balance is not None:
                    estimated_remaining = max(0, pb.known_balance - pb.spent_tracked)
                    # Only sum monetary currencies into the overall USD total
                    if currency in ("USD", "EUR", "GBP"):
                        total_available += estimated_remaining

                providers.append({
                    "provider": pb.provider,
                    "known_balance": pb.known_balance,
                    "spent_tracked": round(pb.spent_tracked, 4),
                    "estimated_remaining": round(estimated_remaining, 4) if estimated_remaining is not None else None,
                    "tier": pb.tier,
                    "currency": currency,
                    "notes": pb.notes,
                    "balance_updated_at": pb.balance_updated_at.isoformat() if pb.balance_updated_at else None,
                })

            # Overall remaining: use config cap when it gives more than provider sum
            # (so override always takes effect when user increases cap)
            from_config = max(0, config.monthly_cap_usd - spent)
            if total_available > 0 and total_available >= from_config:
                remaining = total_available
                cap = total_available + spent
                source = "providers"
            else:
                remaining = from_config
                cap = config.monthly_cap_usd
                source = "config"

            return {
                "monthly_cap": round(cap, 2),
                "spent": round(spent, 4),
                "remaining": round(remaining, 4),
                "percent_used": round((spent / cap) * 100, 1) if cap > 0 else 0,
                "source": source,
                "providers": providers,
            }

    async def get_provider_status(self, provider: str) -> dict | None:
        """Get balance info for a single provider."""
        async with self.session_factory() as session:
            result = await session.execute(
                select(ProviderBalance).where(ProviderBalance.provider == provider)
            )
            pb = result.scalar_one_or_none()
            if not pb:
                return None
            estimated_remaining = None
            if pb.known_balance is not None:
                estimated_remaining = max(0, pb.known_balance - pb.spent_tracked)
            return {
                "provider": pb.provider,
                "known_balance": pb.known_balance,
                "spent_tracked": round(pb.spent_tracked, 4),
                "estimated_remaining": round(estimated_remaining, 4) if estimated_remaining is not None else None,
                "tier": pb.tier,
                "currency": pb.currency or "USD",
                "notes": pb.notes,
            }

    async def update_provider_balance(
        self, provider: str,
        known_balance: float = None,
        tier: str = None,
        currency: str = None,
        notes: str = None,
        reset_spending: bool = False,
    ) -> dict:
        """Update a provider's known balance. Called by user or JARVIS."""
        async with self.session_factory() as session:
            result = await session.execute(
                select(ProviderBalance).where(ProviderBalance.provider == provider)
            )
            pb = result.scalar_one_or_none()
            if not pb:
                pb = ProviderBalance(provider=provider, spent_tracked=0.0)
                session.add(pb)

            if known_balance is not None:
                pb.known_balance = known_balance
                pb.balance_updated_at = datetime.now(timezone.utc)
                if reset_spending:
                    pb.spent_tracked = 0.0
            if tier is not None:
                pb.tier = tier
            if currency is not None:
                pb.currency = currency
            if notes is not None:
                pb.notes = notes

            await session.commit()
            log.info("provider_balance_updated", provider=provider,
                     balance=known_balance, tier=tier, currency=pb.currency)

            return {
                "provider": pb.provider,
                "known_balance": pb.known_balance,
                "spent_tracked": pb.spent_tracked,
                "tier": pb.tier,
                "currency": pb.currency or "USD",
                "notes": pb.notes,
            }

    async def add_provider(
        self, provider: str, api_key: str = None,
        known_balance: float = None, tier: str = "unknown",
        currency: str = "USD", notes: str = None,
    ) -> dict:
        """Add a new provider or update its API key."""
        async with self.session_factory() as session:
            result = await session.execute(
                select(ProviderBalance).where(ProviderBalance.provider == provider)
            )
            pb = result.scalar_one_or_none()
            if not pb:
                pb = ProviderBalance(
                    provider=provider,
                    known_balance=known_balance,
                    tier=tier,
                    currency=currency,
                    notes=notes or "",
                    spent_tracked=0.0,
                    balance_updated_at=datetime.now(timezone.utc) if known_balance else None,
                )
                session.add(pb)
            else:
                if known_balance is not None:
                    pb.known_balance = known_balance
                    pb.balance_updated_at = datetime.now(timezone.utc)
                if tier:
                    pb.tier = tier
                if currency:
                    pb.currency = currency
                if notes:
                    pb.notes = notes

            await session.commit()

        # If API key provided, store it in config
        if api_key:
            from jarvis.config import settings
            key_attr = f"{provider}_api_key"
            if hasattr(settings, key_attr):
                setattr(settings, key_attr, api_key)
                log.info("api_key_updated", provider=provider)

        return {"provider": provider, "known_balance": known_balance, "tier": tier, "currency": currency}

    async def can_spend(self, estimated_cost: float = 0.01) -> bool:
        status = await self.get_status()
        return status["remaining"] >= estimated_cost

    async def get_recommended_tier(self) -> str:
        """Recommend a tier based on per-provider budgets.

        This is now budget-aware at the provider level:
        - If ANY paid provider has > $2 remaining → level1 is fine
        - If paid providers are tight but > $0.50 → level2
        - If all paid providers are near-zero → level3
        - Free providers (Mistral, Ollama) are always available at any tier

        Note: The router further refines this by preferring free providers
        within a tier when budget is tight.
        """
        status = await self.get_status()
        providers = status.get("providers", [])

        # Calculate paid provider availability
        paid_remaining = 0.0
        has_free_provider = False
        for p in providers:
            currency = p.get("currency", "USD")
            tier = p.get("tier", "unknown")
            est = p.get("estimated_remaining")

            if tier == "free":
                has_free_provider = True
                continue

            if est is not None and currency in ("USD", "EUR", "GBP"):
                paid_remaining += est

        # If we have decent paid budget, no restrictions
        if paid_remaining > 5.0:
            return "level1"
        elif paid_remaining > 2.0:
            return "level2"
        elif paid_remaining > 0.50:
            # Tight budget — prefer level2 but don't force level3
            # (free providers like Mistral fill the gaps)
            return "level2"
        elif has_free_provider:
            # Almost no paid budget, but free providers exist
            # Still allow level2 because Mistral Large is free and capable
            return "level2"
        else:
            # Truly broke — no paid budget, no free providers
            return "local_only"

    def _estimate_cost(self, provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
        provider_pricing = PRICING.get(provider, {})
        model_pricing = provider_pricing.get(model, provider_pricing.get("default", {"input": 0, "output": 0}))
        input_cost = (input_tokens / 1_000_000) * model_pricing["input"]
        output_cost = (output_tokens / 1_000_000) * model_pricing["output"]
        return input_cost + output_cost
