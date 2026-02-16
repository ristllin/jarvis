import asyncio
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from jarvis.core.state import StateManager
from jarvis.core.loop import CoreLoop
from jarvis.core.planner import Planner
from jarvis.core.executor import Executor
from jarvis.config import settings


@pytest.mark.asyncio
class TestStateManager:
    async def test_load_or_create_initial(self, session_factory):
        sm = StateManager(session_factory)
        state = await sm.load_or_create()
        assert state["directive"] == settings.initial_directive
        assert state["iteration"] == 0
        assert state["is_paused"] is False
        assert len(state["goals"]) > 0

    async def test_increment_iteration(self, session_factory):
        sm = StateManager(session_factory)
        await sm.load_or_create()
        it1 = await sm.increment_iteration()
        it2 = await sm.increment_iteration()
        assert it2 == it1 + 1

    async def test_pause_resume(self, session_factory):
        sm = StateManager(session_factory)
        await sm.load_or_create()

        await sm.set_paused(True)
        assert await sm.is_paused() is True

        await sm.set_paused(False)
        assert await sm.is_paused() is False

    async def test_update_goals(self, session_factory):
        sm = StateManager(session_factory)
        await sm.load_or_create()

        await sm.update(goals=["New goal 1", "New goal 2"])
        state = await sm.get_state()
        assert state["goals"] == ["New goal 1", "New goal 2"]

    async def test_update_directive(self, session_factory):
        sm = StateManager(session_factory)
        await sm.load_or_create()

        await sm.update(directive="New directive")
        state = await sm.get_state()
        assert state["directive"] == "New directive"

    async def test_heartbeat(self, session_factory):
        sm = StateManager(session_factory)
        await sm.load_or_create()
        await sm.heartbeat()


@pytest.mark.asyncio
class TestCoreLoop:
    async def test_loop_respects_pause(self, session_factory, data_dir):
        sm = StateManager(session_factory)
        await sm.load_or_create()
        await sm.set_paused(True)

        from jarvis.budget.tracker import BudgetTracker
        from jarvis.memory.blob import BlobStorage
        from jarvis.memory.vector import VectorMemory
        from jarvis.observability.logger import FileLogger

        budget = BudgetTracker(session_factory)
        await budget.ensure_config()
        blob = BlobStorage(data_dir)
        vector = VectorMemory(data_dir)
        vector.connect()
        file_logger = FileLogger(data_dir)

        planner = MagicMock()
        executor = MagicMock()

        loop = CoreLoop(
            state_manager=sm,
            planner=planner,
            executor=executor,
            budget=budget,
            blob=blob,
            vector=vector,
            file_logger=file_logger,
        )

        # Run one iteration with a short sleep
        original_sleep = settings.loop_interval_seconds
        settings.loop_interval_seconds = 0.1

        task = asyncio.create_task(loop.run())
        await asyncio.sleep(0.5)
        loop.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        settings.loop_interval_seconds = original_sleep

        # Planner should not have been called since loop is paused
        planner.plan.assert_not_called()

    async def test_loop_runs_iteration(self, session_factory, data_dir):
        sm = StateManager(session_factory)
        await sm.load_or_create()

        from jarvis.budget.tracker import BudgetTracker
        from jarvis.memory.blob import BlobStorage
        from jarvis.memory.vector import VectorMemory
        from jarvis.observability.logger import FileLogger

        budget = BudgetTracker(session_factory)
        await budget.ensure_config()
        blob = BlobStorage(data_dir)
        vector = VectorMemory(data_dir)
        vector.connect()
        file_logger = FileLogger(data_dir)

        mock_plan = {
            "thinking": "test thinking",
            "actions": [],
            "goals_update": None,
            "status_message": "test status",
        }
        planner = MagicMock()
        planner.plan = AsyncMock(return_value=mock_plan)

        executor = MagicMock()
        executor.tools = MagicMock()
        executor.tools.get_tool_names.return_value = ["web_search"]

        loop = CoreLoop(
            state_manager=sm,
            planner=planner,
            executor=executor,
            budget=budget,
            blob=blob,
            vector=vector,
            file_logger=file_logger,
        )

        original_sleep = settings.loop_interval_seconds
        settings.loop_interval_seconds = 0.1

        task = asyncio.create_task(loop.run())
        await asyncio.sleep(0.5)
        loop.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        settings.loop_interval_seconds = original_sleep

        # Planner should have been called at least once
        assert planner.plan.call_count >= 1
