import asyncio
from jarvis.llm.base import LLMProvider, LLMResponse
from jarvis.llm.providers.anthropic import AnthropicProvider
from jarvis.llm.providers.openai import OpenAIProvider
from jarvis.llm.providers.mistral import MistralProvider
from jarvis.llm.providers.grok import GrokProvider
from jarvis.llm.providers.ollama import OllamaProvider
from jarvis.budget.tracker import BudgetTracker
from jarvis.observability.logger import get_logger

log = get_logger("llm_router")

# Maps coding tier requests to their definitions + fallback chain
CODING_TIER_ORDER = ["coding_level1", "coding_level2", "coding_level3", "level3", "local_only"]

# Tier definitions: maps tier -> list of (provider_name, model, cost_tier)
# Free providers (Mistral, Ollama) appear in every tier as fallbacks
# so they're always reachable even when paid budget is exhausted.
DEFAULT_TIERS = {
    "level1": [
        ("anthropic", "claude-opus-4-6", "high"),
        ("openai", "gpt-5.2", "high"),
        ("grok", "grok-4-1-fast-reasoning", "low"),    # Very cheap ($0.20/$0.50 per M) + $25 free
        ("mistral", "mistral-large-latest", "free"),
    ],
    "level2": [
        ("anthropic", "claude-sonnet-4-20250514", "medium"),
        ("openai", "gpt-4o", "medium"),
        ("grok", "grok-4-1-fast-non-reasoning", "low"), # Cheap, no reasoning overhead
        ("mistral", "mistral-large-latest", "free"),
        ("grok", "grok-3-mini", "low"),
        ("anthropic", "claude-haiku-35-20241022", "low"),
        ("mistral", "mistral-small-latest", "free"),
    ],
    "level3": [
        ("mistral", "mistral-small-latest", "free"),
        ("grok", "grok-3-mini", "low"),                 # Very cheap fallback
        ("openai", "gpt-4o-mini", "low"),
        ("ollama", "mistral:7b-instruct", "free"),
    ],
    "local_only": [
        ("mistral", "mistral-small-latest", "free"),
        ("ollama", "mistral:7b-instruct", "free"),
    ],
}

# Coding-specific tier: Devstral + Grok Code models optimized for coding
CODING_TIERS = {
    "coding_level1": [
        ("mistral", "devstral-medium-2507", "free"),    # Best coding model, free
        ("grok", "grok-code-fast-1", "low"),             # xAI code model, very cheap
        ("grok", "grok-4-1-fast-reasoning", "low"),
        ("anthropic", "claude-opus-4-6", "high"),
        ("mistral", "mistral-large-latest", "free"),
    ],
    "coding_level2": [
        ("mistral", "devstral-small-2507", "free"),
        ("mistral", "devstral-medium-2507", "free"),
        ("grok", "grok-code-fast-1", "low"),
        ("anthropic", "claude-sonnet-4-20250514", "medium"),
        ("mistral", "mistral-large-latest", "free"),
    ],
    "coding_level3": [
        ("mistral", "devstral-small-2507", "free"),
        ("mistral", "mistral-small-latest", "free"),
        ("grok", "grok-3-mini", "low"),
        ("openai", "gpt-4o-mini", "low"),
    ],
}


class LLMRouter:
    """Routes LLM requests to the best available provider based on budget and tier."""

    def __init__(self, budget_tracker: BudgetTracker, blob_storage=None):
        self.budget = budget_tracker
        self.blob = blob_storage  # Set after init via set_blob
        self.providers: dict[str, LLMProvider] = {}
        self.tiers = {**DEFAULT_TIERS, **CODING_TIERS}
        self._init_providers()

    def set_blob(self, blob_storage):
        """Set blob storage for recording all LLM calls."""
        self.blob = blob_storage

    def _init_providers(self):
        providers = [
            AnthropicProvider(),
            OpenAIProvider(),
            MistralProvider(),
            GrokProvider(),
            OllamaProvider(),
        ]
        for p in providers:
            if p.is_available():
                self.providers[p.name] = p
                log.info("provider_available", provider=p.name)
            else:
                log.warning("provider_unavailable", provider=p.name)

    async def complete(
        self,
        messages: list[dict],
        tier: str = "level1",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        task_description: str = None,
        min_tier: str = None,
        prefer_free: bool = False,
    ) -> LLMResponse:
        """Route a completion request through the tier chain with fallbacks.

        Args:
            tier: Starting tier preference (e.g. "level1").
            min_tier: Floor tier — budget downgrading cannot go below this.
                      Use "level1" for creator chat, "level2" for important tasks.
            prefer_free: If True, reorder candidates to try free providers first
                         (useful when budget is tight but quality still matters).
        """
        # Determine which tier chain to use
        is_coding_tier = tier.startswith("coding_")
        if is_coding_tier:
            tier_order = CODING_TIER_ORDER
        else:
            tier_order = ["level1", "level2", "level3", "local_only"]

        # Check budget and potentially downgrade tier
        recommended = await self.budget.get_recommended_tier()
        original_tier = tier

        # For coding tiers, map the recommended tier to its coding equivalent
        if is_coding_tier:
            coding_recommended = f"coding_{recommended}" if not recommended.startswith("coding_") else recommended
            if coding_recommended in tier_order and tier_order.index(coding_recommended) > tier_order.index(tier):
                recommended = coding_recommended
            else:
                recommended = tier  # Don't downgrade coding tiers (they're mostly free)

        if not is_coding_tier and tier_order.index(recommended) > tier_order.index(tier):
            # Apply min_tier floor — never downgrade below it
            if min_tier and tier_order.index(recommended) > tier_order.index(min_tier):
                tier = min_tier
                log.info("tier_downgrade_clamped",
                         requested=original_tier, recommended=recommended,
                         clamped_to=min_tier, reason="min_tier_floor")
            else:
                tier = recommended
                log.info("tier_downgraded",
                         requested=original_tier, actual=recommended,
                         reason="budget")

        # Auto-detect if we should prefer free providers
        budget_status = await self.budget.get_status()
        budget_tight = budget_status.get("remaining", 0) < 10.0
        should_prefer_free = prefer_free or budget_tight

        # Try each provider in the tier, then fall through to lower tiers
        start_idx = tier_order.index(tier)
        for current_tier in tier_order[start_idx:]:
            candidates = list(self.tiers.get(current_tier, []))

            # When budget is tight, sort free providers to the front
            if should_prefer_free:
                candidates.sort(key=lambda c: (0 if c[2] == "free" else 1))

            for provider_name, model, cost_tier in candidates:
                if provider_name not in self.providers:
                    continue

                # Budget check for non-free models
                if cost_tier != "free":
                    can = await self.budget.can_spend(0.01)
                    if not can:
                        log.warning("budget_exhausted", skipping=provider_name, model=model)
                        continue

                try:
                    provider = self.providers[provider_name]
                    log.info("llm_request",
                             provider=provider_name, model=model,
                             tier=current_tier, task=task_description,
                             free_preferred=should_prefer_free)

                    # Record request in blob
                    if self.blob:
                        msg_summary = str(messages[-1].get("content", ""))[:500] if messages else ""
                        self.blob.store(
                            event_type="llm_request",
                            content=f"Provider: {provider_name}, Model: {model}, Tier: {current_tier}\nTask: {task_description}\nLast message: {msg_summary}",
                            metadata={"provider": provider_name, "model": model, "tier": current_tier, "task": task_description, "message_count": len(messages)},
                        )

                    response = await provider.complete(
                        messages=messages,
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )

                    # Record usage
                    await self.budget.record_usage(
                        provider=provider_name,
                        model=model,
                        input_tokens=response.input_tokens,
                        output_tokens=response.output_tokens,
                        task_description=task_description,
                    )

                    # Record response in blob
                    if self.blob:
                        self.blob.store(
                            event_type="llm_response",
                            content=f"Provider: {provider_name}, Model: {model}\nTokens: {response.total_tokens}\nResponse: {response.content[:1000]}",
                            metadata={"provider": provider_name, "model": model, "input_tokens": response.input_tokens, "output_tokens": response.output_tokens, "total_tokens": response.total_tokens, "cost_estimate": self.budget._estimate_cost(provider_name, model, response.input_tokens, response.output_tokens)},
                        )

                    log.info("llm_response",
                             provider=provider_name, model=model,
                             tokens=response.total_tokens)
                    return response

                except Exception as e:
                    log.warning("provider_failed",
                                provider=provider_name, model=model,
                                error=str(e))
                    continue

        raise RuntimeError("All LLM providers failed — no response available")

    def get_available_providers(self) -> list[str]:
        return list(self.providers.keys())

    def get_tier_info(self) -> dict:
        info = {}
        for tier_name, candidates in self.tiers.items():
            info[tier_name] = [
                {
                    "provider": p, "model": m, "cost": c,
                    "available": p in self.providers,
                }
                for p, m, c in candidates
            ]
        return info
