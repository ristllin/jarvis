from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from jarvis.models import JarvisState
from jarvis.config import settings
from jarvis.observability.logger import get_logger
from datetime import datetime, timezone, timedelta

log = get_logger("state")

DEFAULT_SHORT_GOALS = [
    "Run self_analysis to verify Grok, providers, and email config",
    "Ensure chat and email responding; use Devstral as fallback over tiny models",
]
DEFAULT_MID_GOALS = [
    "Crypto (coingecko), web search (Tavily) — done. Telegram integration if needed.",
    "Monitor stability; run capability tests; improve self-modification safety.",
]
DEFAULT_LONG_GOALS = [
    "Continuously improve own code, memory, and capabilities",
    "Generate value and resources through work in the world",
    "Expand LLM capabilities and add new provider support",
]

# Short-term memory constraints
STM_MAX_ENTRIES = 50           # Hard cap on number of entries
STM_MAX_AGE_HOURS = 48         # Auto-expire entries older than this
STM_MAX_CONTENT_LENGTH = 500   # Truncate individual entries


class StateManager:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def load_or_create(self) -> dict:
        async with self.session_factory() as session:
            state = await session.get(JarvisState, 1)
            if not state:
                state = JarvisState(
                    id=1,
                    directive=settings.initial_directive,
                    current_goals=DEFAULT_SHORT_GOALS,
                    short_term_goals=DEFAULT_SHORT_GOALS,
                    mid_term_goals=DEFAULT_MID_GOALS,
                    long_term_goals=DEFAULT_LONG_GOALS,
                    short_term_memories=[],
                    active_task=None,
                    loop_iteration=0,
                    is_paused=False,
                )
                session.add(state)
                await session.commit()
                log.info("state_created", directive=state.directive[:80])
            else:
                log.info("state_loaded", iteration=state.loop_iteration)

            return {
                "directive": state.directive,
                "goals": state.current_goals or [],
                "short_term_goals": state.short_term_goals or [],
                "mid_term_goals": state.mid_term_goals or [],
                "long_term_goals": state.long_term_goals or [],
                "short_term_memories": state.short_term_memories or [],
                "active_task": state.active_task,
                "iteration": state.loop_iteration,
                "is_paused": state.is_paused,
                "started_at": str(state.started_at) if state.started_at else None,
            }

    async def update(self, **kwargs):
        async with self.session_factory() as session:
            state = await session.get(JarvisState, 1)
            if not state:
                return
            for key, value in kwargs.items():
                if hasattr(state, key):
                    setattr(state, key, value)
                elif key == "goals":
                    state.current_goals = value
                elif key == "iteration":
                    state.loop_iteration = value
            state.last_heartbeat = datetime.now(timezone.utc)
            await session.commit()

    async def heartbeat(self):
        async with self.session_factory() as session:
            state = await session.get(JarvisState, 1)
            if state:
                state.last_heartbeat = datetime.now(timezone.utc)
                await session.commit()

    async def increment_iteration(self) -> int:
        async with self.session_factory() as session:
            state = await session.get(JarvisState, 1)
            if state:
                state.loop_iteration += 1
                state.last_heartbeat = datetime.now(timezone.utc)
                await session.commit()
                return state.loop_iteration
        return 0

    async def get_state(self) -> dict:
        return await self.load_or_create()

    async def is_paused(self) -> bool:
        async with self.session_factory() as session:
            state = await session.get(JarvisState, 1)
            return state.is_paused if state else False

    async def set_paused(self, paused: bool):
        await self.update(is_paused=paused)

    # ── Short-term memories ──────────────────────────────────────────────

    async def add_short_term_memories(self, entries: list[str], iteration: int = 0):
        """Add one or more short-term memories. Enforces cap by evicting oldest."""
        async with self.session_factory() as session:
            state = await session.get(JarvisState, 1)
            if not state:
                return
            current = list(state.short_term_memories or [])
            now = datetime.now(timezone.utc).isoformat()
            for entry in entries:
                content = entry[:STM_MAX_CONTENT_LENGTH]
                current.append({
                    "content": content,
                    "created_at": now,
                    "iteration": iteration,
                })
            # Evict expired entries first
            current = self._evict_expired(current)
            # Then enforce hard cap (oldest first)
            if len(current) > STM_MAX_ENTRIES:
                current = current[-STM_MAX_ENTRIES:]
            state.short_term_memories = current
            state.last_heartbeat = datetime.now(timezone.utc)
            await session.commit()
            log.info("stm_added", count=len(entries), total=len(current))

    async def replace_short_term_memories(self, entries: list[str], iteration: int = 0):
        """Replace all short-term memories (full overwrite by JARVIS)."""
        now = datetime.now(timezone.utc).isoformat()
        memories = []
        for entry in entries[:STM_MAX_ENTRIES]:
            memories.append({
                "content": entry[:STM_MAX_CONTENT_LENGTH],
                "created_at": now,
                "iteration": iteration,
            })
        await self.update(short_term_memories=memories)
        log.info("stm_replaced", count=len(memories))

    async def remove_short_term_memories(self, indices: list[int]):
        """Remove specific short-term memories by index."""
        async with self.session_factory() as session:
            state = await session.get(JarvisState, 1)
            if not state:
                return
            current = list(state.short_term_memories or [])
            # Remove in reverse order to preserve indices
            for idx in sorted(indices, reverse=True):
                if 0 <= idx < len(current):
                    current.pop(idx)
            state.short_term_memories = current
            state.last_heartbeat = datetime.now(timezone.utc)
            await session.commit()
            log.info("stm_removed", removed=len(indices), remaining=len(current))

    async def clear_short_term_memories(self):
        """Clear all short-term memories."""
        await self.update(short_term_memories=[])
        log.info("stm_cleared")

    async def maintain_short_term_memories(self):
        """Run maintenance: evict expired entries and enforce cap."""
        async with self.session_factory() as session:
            state = await session.get(JarvisState, 1)
            if not state:
                return 0
            current = list(state.short_term_memories or [])
            before = len(current)
            current = self._evict_expired(current)
            if len(current) > STM_MAX_ENTRIES:
                current = current[-STM_MAX_ENTRIES:]
            if len(current) != before:
                state.short_term_memories = current
                await session.commit()
                evicted = before - len(current)
                log.info("stm_maintenance", evicted=evicted, remaining=len(current))
                return evicted
            return 0

    @staticmethod
    def _evict_expired(memories: list[dict]) -> list[dict]:
        """Remove entries older than STM_MAX_AGE_HOURS."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=STM_MAX_AGE_HOURS)
        cutoff_iso = cutoff.isoformat()
        return [m for m in memories if m.get("created_at", "") >= cutoff_iso]
