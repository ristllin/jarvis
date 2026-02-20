import asyncio
import json
import traceback
from dataclasses import dataclass, field
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

# Sleep bounds — kept short because free models (Mistral, Devstral, Ollama) are always available
MIN_SLEEP_SECONDS = 10
MAX_SLEEP_SECONDS = 600   # 10 minutes max (free models mean never fully hibernate)
DEFAULT_SLEEP_SECONDS = 30
# When only tiny models available for reasoning, hibernate longer to avoid degradation
HIBERNATE_WHEN_TINY_ONLY_SECONDS = 600  # 10 min — prefer waiting over tiny-model reasoning drift
TINY_MODELS = frozenset({
    "grok-3-mini", "gpt-4o-mini", "mistral-small-latest",
    "mistral:7b-instruct", "triage-only",
})


@dataclass
class PendingChat:
    """A chat message waiting to be processed by the main loop."""
    message: str
    response_event: asyncio.Event = field(default_factory=asyncio.Event)
    response_text: str = ""
    response_model: str = ""
    response_provider: str = ""
    response_tokens: int = 0
    actions_taken: list = field(default_factory=list)


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
        self._current_model = ""  # Model used for reasoning on last/current task
        # Chat queue — messages from the creator waiting for the next iteration
        self._pending_chats: list[PendingChat] = []

    def enqueue_chat(self, message: str) -> PendingChat:
        """Add a creator chat message to be processed in the next iteration.
        Returns a PendingChat whose response_event will be set when done."""
        pending = PendingChat(message=message)
        self._pending_chats.append(pending)
        self.wake()
        log.info("chat_enqueued", message_len=len(message))
        return pending

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

    def _build_results_summary(self, results: list[dict]) -> str:
        """Build a concise summary of tool execution results for working memory.

        This ensures JARVIS can see what happened in the previous iteration,
        creating a feedback loop: plan → execute → observe results → plan again.
        """
        lines = [f"📋 **Results from {len(results)} action(s) just executed:**\n"]
        for i, r in enumerate(results, 1):
            tool = r.get("tool", "unknown")
            success = r.get("success", False)
            icon = "✅" if success else "❌"
            output = r.get("output", "")
            error = r.get("error", "")

            if success:
                # Truncate long outputs but keep enough to be useful
                summary = output[:600] if output else "(no output)"
                lines.append(f"{i}. {icon} **{tool}**: {summary}")
            else:
                err_msg = error[:300] if error else "(unknown error)"
                lines.append(f"{i}. {icon} **{tool}** FAILED: {err_msg}")

        return "\n".join(lines)

    def _has_free_providers(self, budget_status: dict) -> bool:
        """Check if any free LLM providers are available."""
        for p in budget_status.get("providers", []):
            if p.get("tier") == "free":
                return True
        return False

    def _compute_sleep(self, plan: dict, budget_status: dict) -> float:
        """Determine how long to sleep based on JARVIS's request and budget.

        Key principle: if free providers (Mistral, Devstral, Ollama) are available,
        NEVER auto-throttle to long sleeps. Free models cost nothing — JARVIS should
        stay active and productive using them even when paid budget is depleted.

        When only tiny models are available for reasoning (no Devstral/Mistral Large),
        prefer longer hibernation to avoid quality degradation over time.
        """
        has_free = self._has_free_providers(budget_status)
        model_used = plan.get("_response_model", "") or ""
        is_tiny_model = model_used in TINY_MODELS or (
            model_used.startswith("mistral:") or model_used.startswith("ollama/")
        )
        remaining = budget_status.get("remaining", 100.0)
        actions = plan.get("actions", [])

        # 1. Check if JARVIS explicitly requested a sleep duration
        requested = plan.get("sleep_seconds")
        if requested is not None:
            try:
                requested = float(requested)
                # Cap sleep when free providers exist — JARVIS tends to over-conserve
                effective_max = 120 if has_free else MAX_SLEEP_SECONDS
                sleep = max(MIN_SLEEP_SECONDS, min(effective_max, requested))
                if sleep != requested:
                    log.info("sleep_capped", requested=requested, actual=sleep,
                             reason="free_providers_available" if has_free else "max_limit")
                else:
                    log.info("sleep_requested", requested=requested, actual=sleep)
                return sleep
            except (TypeError, ValueError):
                pass

        # 2. Budget exhausted + only tiny models + no actions → hibernate longer
        if remaining <= 5.0 and not has_free and is_tiny_model and not actions:
            log.info("hibernate_tiny_only",
                     model=model_used, remaining=remaining,
                     reason="Only tiny models available; hibernating to avoid quality drift")
            return HIBERNATE_WHEN_TINY_ONLY_SECONDS

        # 3. Budget-aware auto-throttle — but ONLY if no free providers exist
        if remaining <= 1.0 and not has_free:
            return MAX_SLEEP_SECONDS
        elif remaining <= 1.0 and has_free:
            return 60  # Free models available — stay active, just pace yourself

        # 4. If JARVIS had no actions, moderate sleep (not too long)
        if not actions:
            return 60 if has_free else 120

        # 5. Default
        return DEFAULT_SLEEP_SECONDS

    async def run(self):
        """Main loop — runs forever."""
        log.info("core_loop_starting")

        while self._running:
            sleep_seconds = DEFAULT_SLEEP_SECONDS
            # Drain pending chat messages for this iteration
            chat_messages = list(self._pending_chats)
            self._pending_chats.clear()

            try:
                # Check if paused (but still process chat — creator should always get a reply)
                is_paused = await self.state.is_paused()
                if is_paused and not chat_messages:
                    log.info("loop_paused")
                    await self._broadcast_state("paused")
                    await self._interruptible_sleep(5)
                    continue

                # 1. Load state
                current_state = await self.state.get_state()
                iteration = await self.state.increment_iteration()
                current_state["iteration"] = iteration

                log.info("iteration_start", iteration=iteration,
                         chat_messages=len(chat_messages))
                await self._broadcast_state("running", iteration=iteration)

                # 2. Heartbeat
                await self.state.heartbeat()

                # 3. Get budget status
                budget_status = await self.budget.get_status()

                # 4. Plan (with chat messages injected into context)
                tool_names = self.executor.tools.get_tool_names()
                creator_messages = [c.message for c in chat_messages]
                plan = await self.planner.plan(
                    current_state, budget_status, tool_names,
                    creator_messages=creator_messages,
                )

                thinking = plan.get("thinking", "")
                status_msg = plan.get("status_message", "Processing...")
                chat_reply = plan.get("chat_reply", "")
                triage = plan.get("_triage", {})

                self.blob.store(
                    event_type="plan",
                    content=json.dumps(plan, default=str),
                    metadata={
                        "iteration": iteration,
                        "has_chat": bool(chat_messages),
                        "triage_complexity": triage.get("complexity", ""),
                        "triage_tier": triage.get("tier", ""),
                        "model": plan.get("_response_model", ""),
                    },
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

                # 5b. Feed execution results back into working memory
                # so JARVIS can see what happened on subsequent iterations
                if results:
                    results_summary = self._build_results_summary(results)
                    self.planner.working.add_message("user", results_summary)

                # 6. Store results in long-term vector memory
                for r in results:
                    if r.get("success") and r.get("output"):
                        self.vector.add(MemoryEntry(
                            content=f"[{r['tool']}] {r['output'][:500]}",
                            importance_score=0.5,
                            source=f"tool:{r['tool']}",
                        ))
                    elif not r.get("success") and r.get("error"):
                        self.vector.add(MemoryEntry(
                            content=f"[{r['tool']} FAILED] {r.get('error', '')[:300]}",
                            importance_score=0.6,
                            source=f"tool:{r['tool']}:error",
                        ))

                # 7. Deliver chat reply back to waiting endpoints
                if chat_messages:
                    action_summaries = []
                    for r in results:
                        action_summaries.append({
                            "tool": r.get("tool", ""),
                            "success": r.get("success", False),
                            "output": r.get("output", "")[:300],
                        })
                    if not chat_reply:
                        chat_reply = thinking[:2000] if thinking else status_msg
                    for pending in chat_messages:
                        pending.response_text = chat_reply
                        pending.response_model = plan.get("_response_model", "")
                        pending.response_provider = plan.get("_response_provider", "")
                        pending.response_tokens = plan.get("_response_tokens", 0)
                        pending.actions_taken = action_summaries
                        pending.response_event.set()
                    # Store conversation in long-term memory
                    for pending in chat_messages:
                        self.vector.add(MemoryEntry(
                            content=f"[creator_chat] Creator said: {pending.message[:300]}",
                            importance_score=0.7,
                            source="chat:creator",
                        ))
                    self.vector.add(MemoryEntry(
                        content=f"[jarvis_chat_reply] I replied to creator: {chat_reply[:300]}",
                        importance_score=0.6,
                        source="chat:jarvis",
                    ))
                    log.info("chat_replies_delivered", count=len(chat_messages))

                # 8. Update goals if the plan suggests (supports tiered goals)
                goals_update = plan.get("goals_update")
                if goals_update:
                    if isinstance(goals_update, dict):
                        updates = {}
                        if "short_term" in goals_update:
                            updates["short_term_goals"] = goals_update["short_term"]
                            updates["current_goals"] = goals_update["short_term"]
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

                # 8b. Update short-term memories if JARVIS requests it
                stm_update = plan.get("short_term_memories_update")
                if isinstance(stm_update, dict):
                    stm_add = stm_update.get("add", [])
                    stm_remove = stm_update.get("remove", [])
                    stm_replace = stm_update.get("replace")
                    if stm_replace is not None and isinstance(stm_replace, list):
                        await self.state.replace_short_term_memories(stm_replace, iteration)
                    else:
                        if stm_remove and isinstance(stm_remove, list):
                            await self.state.remove_short_term_memories(stm_remove)
                        if stm_add and isinstance(stm_add, list):
                            await self.state.add_short_term_memories(stm_add, iteration)
                elif isinstance(stm_update, list):
                    # Shorthand: if just a list, treat as full replacement
                    await self.state.replace_short_term_memories(stm_update, iteration)

                # 8c. Auto-add key results as short-term memories
                if results:
                    auto_stm = []
                    for r in results:
                        tool = r.get("tool", "?")
                        success = r.get("success", False)
                        if not success:
                            err = r.get("error", "unknown error")[:200]
                            auto_stm.append(f"[iter {iteration}] {tool} FAILED: {err}")
                        elif r.get("output") and len(r.get("output", "")) > 20:
                            out = r["output"][:200]
                            auto_stm.append(f"[iter {iteration}] {tool} OK: {out}")
                    if auto_stm:
                        await self.state.add_short_term_memories(auto_stm, iteration)

                # 9. Update memory config if JARVIS requests it
                memory_config_update = plan.get("memory_config")
                if isinstance(memory_config_update, dict):
                    working = self.planner.working
                    for key in ("retrieval_count", "max_context_tokens", "decay_factor", "relevance_threshold"):
                        if key in memory_config_update:
                            working.update_config(**{key: memory_config_update[key]})

                # 10. Update active task and current model
                await self.state.update(active_task=status_msg)
                self._current_model = plan.get("_response_model", "") or ""

                # 11. Periodic maintenance (every 10 iterations)
                if iteration % 10 == 0:
                    decay = self.planner.working.memory_config.get("decay_factor", 0.95)
                    self.vector.decay_importance(decay)
                    self.vector.prune_expired()
                    stm_evicted = await self.state.maintain_short_term_memories()
                    log.info("maintenance_complete", iteration=iteration,
                             stm_evicted=stm_evicted)

                # 12. Compute how long to sleep
                sleep_seconds = self._compute_sleep(plan, budget_status)
                self._current_sleep_seconds = sleep_seconds

                # 13. Log iteration complete
                self.file_logger.log(
                    "iteration_complete",
                    iteration=iteration,
                    actions=len(actions),
                    results=len(results),
                    chat_messages=len(chat_messages),
                    budget_remaining=budget_status.get("remaining", 0),
                    next_sleep=sleep_seconds,
                )

                budget_status = await self.budget.get_status()
                await self._broadcast_state("idle",
                                            iteration=iteration,
                                            status_message=status_msg,
                                            budget=budget_status,
                                            next_wake_seconds=sleep_seconds,
                                            triage_complexity=triage.get("complexity", ""),
                                            triage_tier=triage.get("tier", ""),
                                            model=plan.get("_response_model", ""))

                log.info("iteration_complete",
                         iteration=iteration,
                         triage_complexity=triage.get("complexity"),
                         triage_tier=triage.get("tier"),
                         model=plan.get("_response_model"),
                         actions=len(actions),
                         chat_messages=len(chat_messages),
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
                # Still deliver error responses to waiting chat clients
                for pending in chat_messages:
                    if not pending.response_event.is_set():
                        pending.response_text = f"I encountered an error during this iteration: {str(e)}"
                        pending.response_event.set()

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
