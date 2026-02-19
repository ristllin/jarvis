import json
from jarvis.llm.router import LLMRouter
from jarvis.memory.working import WorkingMemory
from jarvis.memory.vector import VectorMemory
from jarvis.safety.prompt_builder import build_system_prompt
from jarvis.observability.logger import get_logger

log = get_logger("planner")

# Triage prompt — kept minimal to save tokens on the cheap model
TRIAGE_SYSTEM_PROMPT = """\
You are a task-complexity triage system for an autonomous AI agent.
Your job is to quickly assess the current situation and decide what level of intelligence is needed.

Respond with ONLY a JSON object:
{
  "complexity": "idle|low|medium|high",
  "tier": "level3|level2|level1",
  "reason": "one sentence why",
  "needs_full_plan": true/false,
  "quick_action": null or {"sleep_seconds": N, "status_message": "..."}
}

Guidelines:
- "low" / level3: Simple routine checks, basic tool calls. A small model can handle it.
- "medium" / level2: Moderate tasks — research, file edits, multi-step plans. Needs a capable model.
- "high" / level1: Complex reasoning, architecture decisions, creator chat, coding agent tasks, self-modification. Needs the best model.

ALWAYS escalate to "high" / level1 if:
- There is a creator chat message (the creator expects a thoughtful reply)
- Self-modification or deployment is needed
- Complex multi-step coding is required
- Strategic planning or goal revision is needed

CRITICAL — BUDGET RULES:
- The agent has FREE LLM providers (Mistral, Devstral, Ollama) that cost NOTHING.
- PAID budget percentage does NOT matter if free providers exist.
- Even if paid budget shows 95% used, the agent can still work productively using free models.
- Do NOT return "idle" or needs_full_plan=false just because the budget looks low.
- If there are active goals or tasks, ALWAYS set needs_full_plan=true so the agent can work on them.
- Only return needs_full_plan=false if goals are genuinely empty AND no tasks are pending.
- When setting quick_action sleep, use short times (30-60s) not long hibernation (300+).
"""


class Planner:
    """Two-phase planner: cheap triage → conditional escalation to powerful models."""

    def __init__(self, router: LLMRouter, working_memory: WorkingMemory, vector_memory: VectorMemory):
        self.router = router
        self.working = working_memory
        # Loop detection: track recent iteration action signatures
        self._recent_action_sigs: list[str] = []
        self._max_sig_history = 10
        self._repeat_threshold = 3  # 3+ identical plans = stuck
        self.vector = vector_memory
        self._consecutive_triage_only = 0  # Track triage-only iterations for forced escalation

    async def plan(self, state: dict, budget_status: dict, tool_names: list[str],
                   creator_messages: list[str] | None = None) -> dict:
        """Generate a plan using two-phase triage.

        Phase 1: Cheap model assesses complexity and picks the right tier.
        Phase 2: Appropriate-tier model generates the full plan (if needed).

        Creator chat always escalates to level1.
        """
        has_chat = bool(creator_messages)

        # Phase 1: Triage (skip if chat — always escalate)
        if has_chat:
            triage = {"complexity": "high", "tier": "level1",
                      "reason": "creator chat", "needs_full_plan": True}
            log.info("triage_skipped", reason="creator_chat", tier="level1")
        else:
            triage = await self._triage(state, budget_status)
            log.info("triage_result",
                     complexity=triage.get("complexity"),
                     tier=triage.get("tier"),
                     needs_full_plan=triage.get("needs_full_plan"),
                     reason=triage.get("reason", ""))

        # If triage says no full plan needed, check for forced escalation
        if not triage.get("needs_full_plan", True):
            self._consecutive_triage_only += 1

            # Force a full plan every 5 triage-only iterations using free models
            # This ensures JARVIS periodically does a real self-assessment
            # and finds work to do rather than endlessly idling
            if self._consecutive_triage_only >= 5:
                log.info("forced_escalation",
                         consecutive_triage_only=self._consecutive_triage_only,
                         reason="periodic self-assessment with free model")
                self._consecutive_triage_only = 0
                triage["complexity"] = "medium"
                triage["tier"] = "level3"  # Use free model (Mistral Small) for the check
                triage["needs_full_plan"] = True
                triage["reason"] = (
                    f"Forced periodic assessment after {self._consecutive_triage_only + 5} "
                    f"idle iterations. Check goals, find productive work using free models."
                )
            else:
                quick = triage.get("quick_action", {}) or {}
                plan = {
                    "thinking": f"[triage] {triage.get('reason', 'idle')}",
                    "actions": [],
                    "sleep_seconds": quick.get("sleep_seconds", 60),
                    "status_message": quick.get("status_message", "Idle — checking for work"),
                    "_triage": triage,
                    "_response_model": "triage-only",
                    "_response_provider": "triage-only",
                    "_response_tokens": 0,
                }
                log.info("plan_from_triage", sleep=plan["sleep_seconds"])
                return plan

        # Phase 2: Full planning with the tier chosen by triage
        self._consecutive_triage_only = 0  # Reset — we're doing a real plan
        selected_tier = triage.get("tier", "level2")
        return await self._full_plan(state, budget_status, tool_names,
                                     creator_messages, selected_tier, triage)

    async def _triage(self, state: dict, budget_status: dict) -> dict:
        """Phase 1: Quick assessment with a cheap model."""
        pct_used = budget_status.get('percent_used', 0)
        remaining = budget_status.get('remaining', 0)
        iteration = state.get('iteration', 0)

        # Build a compact state summary for triage
        short_goals = state.get('short_term_goals', state.get('goals', []))
        active_task = state.get('active_task', 'None')

        triage_msg = (
            f"Iteration #{iteration}. "
            f"Budget: ${remaining:.2f} remaining ({pct_used:.0f}% used). "
            f"Active task: {active_task}. "
            f"Short-term goals: {json.dumps(short_goals[:5])}. "
            f"No creator chat this iteration. "
            f"Assess complexity and decide which tier model should handle planning."
        )

        messages = [
            {"role": "system", "content": TRIAGE_SYSTEM_PROMPT},
            {"role": "user", "content": triage_msg},
        ]

        try:
            response = await self.router.complete(
                messages=messages,
                tier="level3",
                temperature=0.2,
                max_tokens=256,
                task_description="triage",
            )
            result = self._parse_plan(response.content)
            # Validate the result has expected fields
            if "complexity" not in result or "tier" not in result:
                result = {"complexity": "medium", "tier": "level2",
                          "needs_full_plan": True, "reason": "triage parse incomplete"}
            # Ensure tier is valid
            if result.get("tier") not in ("level1", "level2", "level3"):
                result["tier"] = "level2"
            return result
        except Exception as e:
            log.warning("triage_failed", error=str(e))
            # On triage failure, default to medium — don't waste Opus on unknown
            return {"complexity": "medium", "tier": "level2",
                    "needs_full_plan": True, "reason": f"triage error: {e}"}

    async def _full_plan(self, state: dict, budget_status: dict,
                         tool_names: list[str],
                         creator_messages: list[str] | None,
                         tier: str, triage: dict) -> dict:
        """Phase 2: Full planning with the selected tier model."""

        # Build system prompt with tiered goals
        system_prompt = build_system_prompt(
            directive=state["directive"],
            goals=state.get("goals", []),
            budget_status=budget_status,
            available_tools=tool_names,
            short_term_goals=state.get("short_term_goals", []),
            mid_term_goals=state.get("mid_term_goals", []),
            long_term_goals=state.get("long_term_goals", []),
        )
        self.working.set_system_prompt(system_prompt)

        # Retrieve relevant memories
        retrieval_count = self.working.memory_config.get("retrieval_count", 10)
        all_goals = (
            state.get("short_term_goals", [])
            + state.get("mid_term_goals", [])
            + state.get("long_term_goals", [])
            + state.get("goals", [])
        )
        goal_text = " ".join(all_goals)
        active_task = state.get("active_task", "")
        chat_text = " ".join(creator_messages) if creator_messages else ""
        query = f"{goal_text} {active_task} {chat_text}".strip()
        if query:
            relevant = self.vector.search(query, n_results=retrieval_count)
            if relevant:
                threshold = self.working.memory_config.get("relevance_threshold", 0.0)
                if threshold > 0:
                    relevant = [r for r in relevant if (1.0 - (r.get("distance", 0) or 0)) >= threshold]
                self.working.inject_memories(
                    [r["content"] for r in relevant],
                    raw_entries=relevant,
                )

        # Build iteration context message
        pct_used = budget_status.get('percent_used', 0)
        mem_cfg = self.working.memory_config
        stm_entries = state.get("short_term_memories", [])

        iteration_msg = (
            f"This is iteration #{state.get('iteration', 0)}. "
            f"Short-term goals: {json.dumps(state.get('short_term_goals', state.get('goals', [])))}. "
            f"Mid-term goals: {json.dumps(state.get('mid_term_goals', []))}. "
            f"Long-term goals: {json.dumps(state.get('long_term_goals', []))}. "
            f"Active task: {state.get('active_task', 'None')}. "
            f"Budget remaining: ${budget_status.get('remaining', 0):.2f} ({pct_used:.0f}% used). "
            f"Memory config: retrieval_count={mem_cfg['retrieval_count']}, "
            f"threshold={mem_cfg['relevance_threshold']}, "
            f"decay={mem_cfg['decay_factor']}. "
            f"Memories injected this iteration: {len(self.working.injected_memories)}. "
            f"Triage assessment: complexity={triage.get('complexity')}, reason={triage.get('reason', '')}. "
            f"You are running on tier={tier} for this iteration. "
            f"Plan your next actions. Use tools to accomplish your goals. "
            f"You can update goals at any tier using goals_update with keys: short_term, mid_term, long_term. "
            f"You can tune memory_config: retrieval_count (1-100), relevance_threshold (0-1), decay_factor (0.5-1). "
            f"Remember: you can use coding_agent for complex code changes and self_modify for git/deploy. "
            f"For each action, you can specify \"tier\": \"level1\"|\"level2\"|\"level3\" to control "
            f"which model handles that tool (e.g. coding_agent with tier=level1 for hard tasks, level2 for simpler ones). "
            f"Set sleep_seconds to control when you wake next (10-3600). "
            f"Remember: Mistral, Devstral, and Ollama are FREE — use them to stay productive "
            f"even when paid budget is low. Only sleep long if you truly have zero goals or tasks."
        )

        # Inject short-term memories (operational notes from recent iterations)
        if stm_entries:
            stm_block = f"\n\n📝 **SHORT-TERM MEMORIES** ({len(stm_entries)}/{50} slots):\n"
            for i, m in enumerate(stm_entries):
                content = m.get("content", "") if isinstance(m, dict) else str(m)
                created = m.get("created_at", "?") if isinstance(m, dict) else "?"
                stm_block += f"  [{i}] {content}\n"
            stm_block += (
                "\nYou can manage these with `short_term_memories_update` in your response. "
                "Use `{\"add\": [...]}` to add notes, `{\"remove\": [0, 3]}` to remove by index, "
                "or `{\"replace\": [...]}` to overwrite all. "
                "Old entries auto-expire after 48h. Max 50 entries."
            )
            iteration_msg += stm_block

        # Loop detection warning
        loop_warning = self._check_stuck_loop()
        if loop_warning:
            iteration_msg += f"\n\n⚠️ **STUCK LOOP DETECTED**: {loop_warning}"

        # Inject creator chat messages
        if creator_messages:
            chat_block = "\n\n🔔 **CREATOR CHAT — your creator is talking to you directly. " \
                         "You MUST include a `chat_reply` field in your response.**\n"
            for i, msg in enumerate(creator_messages, 1):
                chat_block += f"\nCreator message {i}: {msg}"
            chat_block += (
                "\n\nRespond to the creator in `chat_reply` (markdown is fine). "
                "You can ALSO take actions in `actions` if the creator asked you to do something. "
                "The creator sees your full context, tools, goals — be specific and honest."
            )
            iteration_msg += chat_block

        self.working.add_message("user", iteration_msg)

        # Call LLM at the triage-selected tier
        # For creator chat: enforce min_tier=level1 so budget never downgrades below it
        # For autonomous planning: enforce min_tier=level2 so we never fall to junk models
        is_chat = bool(creator_messages)
        messages = self.working.get_messages_for_llm()
        response = await self.router.complete(
            messages=messages,
            tier=tier,
            temperature=0.7,
            max_tokens=4096,
            task_description="planning" if not is_chat else "chat_iteration",
            min_tier="level1" if is_chat else "level2",
        )

        # Parse response
        plan = self._parse_plan(response.content)
        plan["_triage"] = triage
        plan["_response_model"] = response.model
        plan["_response_provider"] = response.provider
        plan["_response_tokens"] = response.total_tokens
        self.working.add_message("assistant", response.content)

        # Track action signature for loop detection
        self._track_action_sig(plan)

        log.info("plan_generated",
                 tier=tier,
                 model=response.model,
                 actions=len(plan.get("actions", [])),
                 has_chat_reply=bool(plan.get("chat_reply")),
                 thinking=plan.get("thinking", "")[:100])
        return plan

    def _get_action_sig(self, plan: dict) -> str:
        """Create a short signature of the plan's actions for loop detection."""
        actions = plan.get("actions", [])
        if not actions:
            return "no_actions"
        parts = []
        for a in actions[:5]:
            tool = a.get("tool", "?")
            # For file_write, include the path to detect repeated writes to same files
            path = a.get("parameters", {}).get("path", "")
            if path:
                parts.append(f"{tool}:{path}")
            else:
                parts.append(tool)
        return "|".join(parts)

    def _track_action_sig(self, plan: dict):
        """Record this iteration's action signature."""
        sig = self._get_action_sig(plan)
        self._recent_action_sigs.append(sig)
        if len(self._recent_action_sigs) > self._max_sig_history:
            self._recent_action_sigs.pop(0)

    def _check_stuck_loop(self) -> str | None:
        """Check if JARVIS appears stuck repeating the same actions."""
        if len(self._recent_action_sigs) < self._repeat_threshold:
            return None

        recent = self._recent_action_sigs[-self._repeat_threshold:]
        if len(set(recent)) == 1 and recent[0] != "no_actions":
            sig = recent[0]
            log.warning("stuck_loop_detected", signature=sig,
                        repeat_count=self._repeat_threshold)
            return (
                f"You have produced the same action pattern ({sig}) for the last "
                f"{self._repeat_threshold} iterations. You are stuck in a loop. "
                f"STOP doing the same thing. Try a COMPLETELY different approach: "
                f"1) Use coding_agent instead of file_write for complex code changes. "
                f"2) Check if the files you're trying to create already exist (use file_read first). "
                f"3) Update your goals to reflect what's actually done vs not done. "
                f"4) If you can't make progress, set a long sleep and wait for creator guidance. "
                f"5) NEVER dump entire file contents in file_write — use coding_agent for multi-file work."
            )

        # Also detect no_actions loops (idle stuck)
        no_action_count = sum(1 for s in self._recent_action_sigs[-5:] if s == "no_actions")
        if no_action_count >= 4:
            return (
                "You've had no actions for 4+ iterations in a row. "
                "Don't just sleep — you have FREE models (Mistral, Devstral, Ollama). "
                "Find something productive: improve your code, build a new tool, "
                "research something useful, write skills, or work on your goals. "
                "If you genuinely have no goals, CREATE some — you're an autonomous agent."
            )

        return None

    def _parse_plan(self, content: str) -> dict:
        """Parse the LLM response into a structured plan.

        Handles: raw JSON, markdown-fenced JSON (```json ... ```),
        double-nested responses (JSON inside a 'thinking' field), and
        partial/truncated JSON.
        """
        # Strip markdown code fences if present
        cleaned = content.strip()
        if cleaned.startswith("```"):
            # Remove opening fence (```json or ```)
            first_newline = cleaned.find("\n")
            if first_newline > 0:
                cleaned = cleaned[first_newline + 1:]
            # Remove closing fence
            if cleaned.rstrip().endswith("```"):
                cleaned = cleaned.rstrip()[:-3].rstrip()

        # Attempt 1: Direct JSON parse
        plan = self._try_json(cleaned)
        if plan:
            # Check for double-nesting: if 'thinking' contains JSON with 'actions'
            plan = self._unwrap_nested(plan)
            return plan

        # Attempt 2: Find JSON object in the content
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start >= 0 and end > start:
            plan = self._try_json(cleaned[start:end])
            if plan:
                plan = self._unwrap_nested(plan)
                return plan

        # Attempt 3: Try to fix truncated JSON (missing closing braces)
        if start >= 0:
            fragment = cleaned[start:]
            for extra in ["}", "]}", '"]}']:
                plan = self._try_json(fragment + extra)
                if plan:
                    plan = self._unwrap_nested(plan)
                    log.warning("plan_json_repaired", extra_chars=extra)
                    return plan

        # Fallback: no actions
        return {
            "thinking": content[:2000],
            "actions": [],
            "goals_update": None,
            "status_message": "Processing...",
        }

    def _try_json(self, text: str) -> dict | None:
        """Try to parse JSON, return None on failure."""
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, ValueError):
            pass
        return None

    def _unwrap_nested(self, plan: dict) -> dict:
        """Handle double-nested responses where the real plan is inside 'thinking'.

        Some models return: {"thinking": "```json\\n{\\n  \\"thinking\\": ..., \\"actions\\": [...]}"}
        This detects and unwraps that pattern.
        """
        thinking = plan.get("thinking", "")
        actions = plan.get("actions", [])

        # If there are no actions but 'thinking' looks like it contains JSON with actions
        if not actions and isinstance(thinking, str) and '"actions"' in thinking:
            # Strip markdown fences inside thinking
            inner = thinking.strip()
            if inner.startswith("```"):
                first_nl = inner.find("\n")
                if first_nl > 0:
                    inner = inner[first_nl + 1:]
                if inner.rstrip().endswith("```"):
                    inner = inner.rstrip()[:-3].rstrip()

            inner_plan = self._try_json(inner)
            if not inner_plan:
                start = inner.find("{")
                end = inner.rfind("}") + 1
                if start >= 0 and end > start:
                    inner_plan = self._try_json(inner[start:end])

            if inner_plan and isinstance(inner_plan, dict):
                # Merge: use inner plan but preserve outer metadata
                if inner_plan.get("actions"):
                    log.info("unwrapped_nested_plan",
                             inner_actions=len(inner_plan.get("actions", [])))
                    return inner_plan

        return plan
