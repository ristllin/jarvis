import asyncio
from datetime import datetime, timezone, timedelta
from jarvis.core.state import StateManager
from jarvis.observability.logger import get_logger

log = get_logger("watchdog")


class Watchdog:
    """Monitors the core loop heartbeat and restarts if stuck."""

    def __init__(self, state_manager: StateManager, timeout_seconds: int = 600):
        self.state = state_manager
        self.timeout = timeout_seconds
        self._loop_task = None
        self._restart_callback = None

    def set_loop_task(self, task: asyncio.Task, restart_callback):
        self._loop_task = task
        self._restart_callback = restart_callback

    async def run(self):
        """Run the watchdog monitoring loop."""
        log.info("watchdog_started", timeout=self.timeout)
        while True:
            await asyncio.sleep(30)
            try:
                state = await self.state.get_state()
                if state.get("is_paused"):
                    continue

                # Check if loop task is still alive
                if self._loop_task and self._loop_task.done():
                    exc = self._loop_task.exception() if not self._loop_task.cancelled() else None
                    log.error("loop_died", exception=str(exc) if exc else "cancelled")
                    if self._restart_callback:
                        log.info("watchdog_restarting_loop")
                        self._restart_callback()
            except Exception as e:
                log.error("watchdog_error", error=str(e))
