import asyncio
import json
import traceback
from datetime import datetime, timezone
from jarvis.core.state import StateManager
from jarvis.core.planner import Planner
from jarvis.core.executor import Executor
from jarvis.budget.tracker import BudgetTracker
from jarvis.memory.blob import BlobStorage
from jarvis.memory.vector import VectorMemory
from jarvis.memory.models import MemoryEntry
from jarvis.safety.validator import SafetyValidator
from jarvis.config import settings
from jarvis.observability.logger import get_logger, FileLogger

log = get_logger("core_loop")

# Sleep bounds
MIN_SLEEP_SECONDS = 10
MAX_SLEEP_SECONDS = 3600  # 1 hour
DEFAULT_SLEEP_SECONDS = 30


class CoreLoop:
    """The persistent never-ending execution loop of Jarvis."""

    def __init__(
        self,
        state_manager: StateManager,
        planner: Planner,
        executor: Executor,
        budget: BudgetTracker,
        blob: BlobStorage,
        vector: VectorMemory,
        file_logger: FileLogger,
        broadcast_fn=None,
    ):
        self.state = state_manager
        self.planner = planner
        self.executor = executor
        self.budget = budget
        self.blob = blob
        self.vector = vector
        self.file_logger = file_logger
        self.broadcast = broadcast_fn or (lambda x: None)
        self._running = True
        # Wake event — set by chat or external triggers to interrupt sleep
        self._wake_event = asyncio.Event()
        self._current_sleep_seconds = DEFAULT_SLEEP_SECONDS

    def wake(self):
        """Interrupt the current sleep and start the next iteration immediately.
        Called by the chat endpoint or other external triggers."""
        self._wake_event.set()
        log.info("wake_triggered")

    async def _interruptible_sleep(self, seconds: float):
        """Sleep for up to `seconds`, but wake early if wake() is called."""
        self._wake_event.clear()
        try:
            await asyncio.wait_for(self._wake_event.wait(), timeout=seconds)
            log.info("sleep_interrupted", slept_less_than=seconds)
        except asyncio.TimeoutError:
            pass  # Normal — full sleep completed

    def _compute_sleep(self, plan: dict, budget_status: dict) -> float:
        """Determine how long to sleep based on JARVIS's request and budget."""
        # 1. Check if JARVIS explicitly requested a sleep duration
        requested = plan.get("sleep_seconds")
        if requested is not None:
            try:
                requested = float(requested)
                sleep = max(MIN_SLEEP_SECONDS, min(MAX_SLEEP_SECONDS, requested))
                log.info("sleep_requested", requested=requested, actual=sleep)
                return sleep
            except (TypeError, ValueError):
                pass

        # 2. Budget-aware auto-throttle
        pct_used = budget_status.get("percent_used", 0)
        remaining = budget_status.get("remaining", 100.0)

        if remaining <= 1.0:
            # Almost out of budget — sleep long, only wake for chat
            return MAX_SLEEP_SECONDS
        elif pct_used > 90:
            return 600  # 10 minutes
        elif pct_used > 75:
            return 180  # 3 minutes
        elif pct_used > 50:
            return 60   # 1 minute

        # 3. If JARVIS had no actions, increase sleep (nothing to do)
        actions = plan.get("actions", [])
        if not actions:
            return 120  # 2 minutes if idle

        # 4. Default
        return DEFAULT_SLEEP_SECONDS

    async def run(self):
        """Main loop — runs forever."""
        log.info("core_loop_starting")

        while self._running:
            sleep_seconds = DEFAULT_SLEEP_SECONDS

            try:
                # Check if paused
                if await self.state.is_paused():
                    log.info("loop_paused")
                    await self._broadcast_state("paused")
                    await self._interruptible_sleep(5)
                    continue

                # 1. Load state
                current_state = await self.state.get_state()
                iteration = await self.state.increment_iteration()
                current_state["iteration"] = iteration

                log.info("iteration_start", iteration=iteration)
                await self._broadcast_state("running", iteration=iteration)

                # 2. Heartbeat
                await self.state.heartbeat()

                # 3. Get budget status
                budget_status = await self.budget.get_status()

                # 4. Plan
                tool_names = self.executor.tools.get_tool_names()
                plan = await self.planner.plan(current_state, budget_status, tool_names)

                thinking = plan.get("thinking", "")
                status_msg = plan.get("status_message", "Processing...")

                self.blob.store(
                    event_type="plan",
                    content=json.dumps(plan, default=str),
                    metadata={"iteration": iteration},
                )
                await self._broadcast_state("planning", status_message=status_msg, thinking=thinking[:200])

                # 5. Validate + Execute actions
                actions = plan.get("actions", [])
                results = []
                if actions:
                    results = await self.executor.execute_plan(plan)

                    await self._broadcast_state("executing",
                                                actions_count=len(actions),
                                                results_count=len(results))

                # 6. Store results in memory
                for r in results:
                    if r.get("success") and r.get("output"):
                        self.vector.add(MemoryEntry(
                            content=f"[{r['tool']}] {r['output'][:500]}",
                            importance_score=0.4,
                            source=f"tool:{r['tool']}",
                        ))

                # 7. Update goals if the plan suggests (supports tiered goals)
                goals_update = plan.get("goals_update")
                if goals_update:
                    if isinstance(goals_update, dict):
                        # Tiered goals: {short_term: [...], mid_term: [...], long_term: [...]}
                        updates = {}
                        if "short_term" in goals_update:
                            updates["short_term_goals"] = goals_update["short_term"]
                            updates["current_goals"] = goals_update["short_term"]  # compat
                        if "mid_term" in goals_update:
                            updates["mid_term_goals"] = goals_update["mid_term"]
                        if "long_term" in goals_update:
                            updates["long_term_goals"] = goals_update["long_term"]
                        if updates:
                            await self.state.update(**updates)
                            log.info("goals_updated_tiered", updates=list(updates.keys()))
                    elif isinstance(goals_update, list):
                        await self.state.update(goals=goals_update)
                        log.info("goals_updated", goals=goals_update)

                # 8. Update memory config if JARVIS requests it
                memory_config_update = plan.get("memory_config")
                if isinstance(memory_config_update, dict):
                    working = self.planner.working
                    for key in ("retrieval_count", "max_context_tokens", "decay_factor", "relevance_threshold"):
                        if key in memory_config_update:
                            working.update_config(**{key: memory_config_update[key]})

                # 9. Update active task
                await self.state.update(active_task=status_msg)

                # 10. Periodic maintenance (every 10 iterations)
                if iteration % 10 == 0:
                    decay = self.planner.working.memory_config.get("decay_factor", 0.95)
                    self.vector.decay_importance(decay)
                    self.vector.prune_expired()
                    log.info("maintenance_complete", iteration=iteration)

                # 11. Compute how long to sleep
                sleep_seconds = self._compute_sleep(plan, budget_status)
                self._current_sleep_seconds = sleep_seconds

                # 12. Log iteration complete
                self.file_logger.log(
                    "iteration_complete",
                    iteration=iteration,
                    actions=len(actions),
                    results=len(results),
                    budget_remaining=budget_status.get("remaining", 0),
                    next_sleep=sleep_seconds,
                )

                budget_status = await self.budget.get_status()
                await self._broadcast_state("idle",
                                            iteration=iteration,
                                            status_message=status_msg,
                                            budget=budget_status,
                                            next_wake_seconds=sleep_seconds)

                log.info("iteration_complete",
                         iteration=iteration,
                         actions=len(actions),
                         budget_remaining=budget_status.get("remaining"),
                         next_sleep=sleep_seconds)

            except Exception as e:
                log.error("iteration_error",
                          error=str(e),
                          traceback=traceback.format_exc())
                self.blob.store(
                    event_type="error",
                    content=f"Loop error: {str(e)}\n{traceback.format_exc()}",
                )
                await self._broadcast_state("error", error=str(e))

            # Sleep between iterations — interruptible by wake()
            await self._interruptible_sleep(sleep_seconds)

    async def _broadcast_state(self, status: str, **extra):
        """Send state update to WebSocket subscribers."""
        try:
            msg = {
                "type": "state_update",
                "status": status,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **extra,
            }
            if asyncio.iscoroutinefunction(self.broadcast):
                await self.broadcast(msg)
            else:
                self.broadcast(msg)
        except Exception:
            pass

    def stop(self):
        self._running = False
