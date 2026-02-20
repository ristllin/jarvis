from datetime import UTC, datetime

from jarvis.config import settings
from jarvis.models import JarvisState
from jarvis.observability.logger import get_logger

log = get_logger("state")

DEFAULT_SHORT_GOALS = ["Initialize systems and understand my capabilities"]
DEFAULT_MID_GOALS = ["Develop self-improvement projects", "Test and document all tools"]
DEFAULT_LONG_GOALS = [
    "Continuously improve own code, memory, and capabilities",
    "Generate value and resources through work in the world",
    "Expand LLM capabilities and add new provider support",
]


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
            state.last_heartbeat = datetime.now(UTC)
            await session.commit()

    async def heartbeat(self):
        async with self.session_factory() as session:
            state = await session.get(JarvisState, 1)
            if state:
                state.last_heartbeat = datetime.now(UTC)
                await session.commit()

    async def increment_iteration(self) -> int:
        async with self.session_factory() as session:
            state = await session.get(JarvisState, 1)
            if state:
                state.loop_iteration += 1
                state.last_heartbeat = datetime.now(UTC)
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
