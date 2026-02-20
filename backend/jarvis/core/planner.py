import json

from jarvis.llm.router import LLMRouter
from jarvis.memory.vector import VectorMemory
from jarvis.memory.working import WorkingMemory
from jarvis.observability.logger import get_logger
from jarvis.safety.prompt_builder import build_system_prompt

log = get_logger("planner")


def _ensure_list(value) -> list:
    """Coerce a value to a list safely — handles None, dicts, strings, etc."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.values()) if value else []
    return [value]


class Planner:
    """Single-phase Level 1 planner — always uses the best available model.

    The planner always runs at level1 tier (Mistral Large is free there),
    producing a full plan with per-action tier assignments. This eliminates
    the old two-phase triage where cheap models made poor escalation decisions.
    """

    def __init__(self, router: LLMRouter, working_memory: WorkingMemory, vector_memory: VectorMemory):
        self.router = router
        self.working = working_memory
        self.vector = vector_memory
        self._recent_action_sigs: list[str] = []
        self._max_sig_history = 10
        self._repeat_threshold = 3
        self._last_iteration_summary: str = ""

    async def plan(
        self, state: dict, budget_status: dict, tool_names: list[str], creator_messages: list[str] | None = None
    ) -> dict:
        """Generate a plan using Level 1 intelligence.

        Always uses level1 tier for planning (Mistral Large is free).
        The plan includes per-action tier assignments so execution
        can use cheaper models where appropriate.
        """
        return await self._full_plan(state, budget_status, tool_names, creator_messages)

    def set_last_iteration_summary(self, summary: str):
        """Store a summary of the previous iteration's outcome for context."""
        self._last_iteration_summary = summary

    async def _full_plan(
        self, state: dict, budget_status: dict, tool_names: list[str], creator_messages: list[str] | None
    ) -> dict:
        """Generate a full plan at level1 tier."""

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

        # Retrieve relevant memories (configurable count)
        retrieval_count = self.working.memory_config.get("retrieval_count", 10)
        all_goals = (
            _ensure_list(state.get("short_term_goals"))
            + _ensure_list(state.get("mid_term_goals"))
            + _ensure_list(state.get("long_term_goals"))
            + _ensure_list(state.get("goals"))
        )
        goal_text = " ".join(str(g) for g in all_goals)
        active_task = state.get("active_task", "")
        chat_text = " ".join(creator_messages) if creator_messages else ""
        query = f"{active_task} {chat_text} {goal_text}".strip()
        if query:
            relevant = self.vector.search(query, n_results=retrieval_count)
            if relevant:
                # Filter by relevance threshold if set
                threshold = self.working.memory_config.get("relevance_threshold", 0.0)
                if threshold > 0:
                    relevant = [r for r in relevant if (1.0 - (r.get("distance", 0) or 0)) >= threshold]
                self.working.inject_memories(
                    [r["content"] for r in relevant],
                    raw_entries=relevant,
                )

        # Build structured iteration context
        pct_used = budget_status.get("percent_used", 0)
        mem_cfg = self.working.memory_config
        stm_entries = state.get("short_term_memories", [])
        iteration = state.get("iteration", 0)

        sections = []
        sections.append(f'<iteration number="{iteration}">')

        sections.append("<goals>")
        sections.append(
            f"  <short_term>{json.dumps(_ensure_list(state.get('short_term_goals', state.get('goals', []))))}</short_term>"
        )
        sections.append(f"  <mid_term>{json.dumps(_ensure_list(state.get('mid_term_goals', [])))}</mid_term>")
        sections.append(f"  <long_term>{json.dumps(_ensure_list(state.get('long_term_goals', [])))}</long_term>")
        sections.append(f"  <active_task>{state.get('active_task', 'None')}</active_task>")
        sections.append("</goals>")

        sections.append(
            f'<budget remaining="${budget_status.get("remaining", 0):.2f}" percent_used="{pct_used:.0f}%" />'
        )

        sections.append(
            f'<memory retrieval_count="{mem_cfg["retrieval_count"]}" '
            f'threshold="{mem_cfg["relevance_threshold"]}" '
            f'decay="{mem_cfg["decay_factor"]}" '
            f'injected="{len(self.working.injected_memories)}" />'
        )

        if self._last_iteration_summary:
            sections.append(f"<last_iteration_outcome>{self._last_iteration_summary}</last_iteration_outcome>")

        if stm_entries:
            sections.append(f'<scratchpad slots="{len(stm_entries)}/50">')
            for i, m in enumerate(stm_entries):
                content = m.get("content", "") if isinstance(m, dict) else str(m)
                sections.append(f"  [{i}] {content}")
            sections.append("</scratchpad>")
            sections.append(
                "Manage scratchpad with `short_term_memories_update`: "
                '{"add": [...]}, {"remove": [indices]}, or {"replace": [...]}.'
            )

        loop_warning = self._check_stuck_loop()
        if loop_warning:
            sections.append(f'<warning type="stuck_loop">{loop_warning}</warning>')

        if creator_messages:
            sections.append("<creator_chat>")
            sections.append("Your creator is talking to you. You MUST include a `chat_reply` field.")
            for i, msg in enumerate(creator_messages, 1):
                sections.append(f"  Message {i}: {msg}")
            sections.append("Respond in `chat_reply` (markdown OK). Also take actions if asked.")
            sections.append("</creator_chat>")

        if iteration > 0 and iteration % 5 == 0:
            sections.append('<goal_review required="true">')
            sections.append(
                "This is a goal review iteration. You MUST include `goals_update` in your response. "
                "Review your short/mid/long-term goals. Update completed ones, add new ones, "
                "remove stale ones. Reflect on progress."
            )
            sections.append("</goal_review>")

        sections.append("<instructions>")
        sections.append(
            "Plan your next actions. Assign `tier` per action: "
            "level1/coding_level1 (complex), level2/coding_level2 (moderate), level3 (simple). "
            "Free models cost $0."
        )
        sections.append("</instructions>")

        sections.append("</iteration>")

        iteration_msg = "\n".join(sections)
        self.working.add_message("user", iteration_msg)

        is_chat = bool(creator_messages)
        messages = self.working.get_messages_for_llm()
        response = await self.router.complete(
            messages=messages,
            tier="level1",
            temperature=0.7,
            max_tokens=4096,
            task_description="planning" if not is_chat else "chat_iteration",
            min_tier="level1",
        )

        # Parse response
        plan = self._parse_plan(response.content)
        plan["_response_model"] = response.model
        plan["_response_provider"] = response.provider
        plan["_response_tokens"] = response.total_tokens
        self.working.add_message("assistant", response.content)

        self._track_action_sig(plan)

        log.info(
            "plan_generated",
            model=response.model,
            provider=response.provider,
            actions=len(plan.get("actions", [])),
            has_chat_reply=bool(plan.get("chat_reply")),
            thinking=plan.get("thinking", "")[:100],
        )
        return plan

    def _get_action_sig(self, plan: dict) -> str:
        """Create a short signature of the plan's actions for loop detection."""
        actions = plan.get("actions", [])
        if not actions:
            return "no_actions"
        parts = []
        for a in actions[:5]:
            tool = a.get("tool", "?")
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

        recent = self._recent_action_sigs[-self._repeat_threshold :]
        if len(set(recent)) == 1 and recent[0] != "no_actions":
            sig = recent[0]
            log.warning("stuck_loop_detected", signature=sig, repeat_count=self._repeat_threshold)
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
        """Parse the LLM response into a structured plan."""
        cleaned = content.strip()
        if cleaned.startswith("```"):
            first_newline = cleaned.find("\n")
            if first_newline > 0:
                cleaned = cleaned[first_newline + 1 :]
            if cleaned.rstrip().endswith("```"):
                cleaned = cleaned.rstrip()[:-3].rstrip()

        plan = self._try_json(cleaned)
        if plan:
            plan = self._unwrap_nested(plan)
            return plan

        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start >= 0 and end > start:
            plan = self._try_json(cleaned[start:end])
            if plan:
                plan = self._unwrap_nested(plan)
                return plan

        if start >= 0:
            fragment = cleaned[start:]
            for extra in ["}", "]}", '"]}']:
                plan = self._try_json(fragment + extra)
                if plan:
                    plan = self._unwrap_nested(plan)
                    log.warning("plan_json_repaired", extra_chars=extra)
                    return plan

        return {
            "thinking": content,
            "actions": [],
            "goals_update": None,
            "status_message": "Processing...",
        }

    def _try_json(self, text: str) -> dict | None:
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, ValueError):
            pass
        return None

    def _unwrap_nested(self, plan: dict) -> dict:
        """Handle double-nested responses where the real plan is inside 'thinking'."""
        thinking = plan.get("thinking", "")
        actions = plan.get("actions", [])

        if not actions and isinstance(thinking, str) and '"actions"' in thinking:
            inner = thinking.strip()
            if inner.startswith("```"):
                first_nl = inner.find("\n")
                if first_nl > 0:
                    inner = inner[first_nl + 1 :]
                if inner.rstrip().endswith("```"):
                    inner = inner.rstrip()[:-3].rstrip()

            inner_plan = self._try_json(inner)
            if not inner_plan:
                start = inner.find("{")
                end = inner.rfind("}") + 1
                if start >= 0 and end > start:
                    inner_plan = self._try_json(inner[start:end])

            if inner_plan and isinstance(inner_plan, dict) and inner_plan.get("actions"):
                log.info("unwrapped_nested_plan", inner_actions=len(inner_plan.get("actions", [])))
                return inner_plan

        return plan
