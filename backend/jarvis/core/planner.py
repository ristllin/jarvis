import json
from jarvis.llm.router import LLMRouter
from jarvis.memory.working import WorkingMemory
from jarvis.memory.vector import VectorMemory
from jarvis.safety.prompt_builder import build_system_prompt
from jarvis.observability.logger import get_logger

log = get_logger("planner")


class Planner:
    """Uses Level 1 LLM to plan the next actions based on current state."""

    def __init__(self, router: LLMRouter, working_memory: WorkingMemory, vector_memory: VectorMemory):
        self.router = router
        self.working = working_memory
        self.vector = vector_memory

    async def plan(self, state: dict, budget_status: dict, tool_names: list[str]) -> dict:
        """Generate a plan for the next iteration."""

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
        all_goals = (
            state.get("short_term_goals", [])
            + state.get("mid_term_goals", [])
            + state.get("long_term_goals", [])
            + state.get("goals", [])
        )
        goal_text = " ".join(all_goals)
        if goal_text:
            relevant = self.vector.search(goal_text, n_results=3)
            if relevant:
                self.working.inject_memories([r["content"] for r in relevant])

        # Add iteration context
        pct_used = budget_status.get('percent_used', 0)
        iteration_msg = (
            f"This is iteration #{state.get('iteration', 0)}. "
            f"Short-term goals: {json.dumps(state.get('short_term_goals', state.get('goals', [])))}. "
            f"Mid-term goals: {json.dumps(state.get('mid_term_goals', []))}. "
            f"Long-term goals: {json.dumps(state.get('long_term_goals', []))}. "
            f"Active task: {state.get('active_task', 'None')}. "
            f"Budget remaining: ${budget_status.get('remaining', 0):.2f} ({pct_used:.0f}% used). "
            f"Plan your next actions. Use tools to accomplish your goals. "
            f"You can update goals at any tier using goals_update with keys: short_term, mid_term, long_term. "
            f"Remember: you can use coding_agent for complex code changes and self_modify for git/deploy. "
            f"Set sleep_seconds to control when you wake next (10-3600). "
            f"If you have nothing to do, set a long sleep and conserve budget."
        )
        self.working.add_message("user", iteration_msg)

        # Call Level 1 LLM
        messages = self.working.get_messages_for_llm()
        response = await self.router.complete(
            messages=messages,
            tier="level1",
            temperature=0.7,
            max_tokens=4096,
            task_description="planning",
        )

        # Parse response
        plan = self._parse_plan(response.content)
        self.working.add_message("assistant", response.content)

        log.info("plan_generated",
                 actions=len(plan.get("actions", [])),
                 thinking=plan.get("thinking", "")[:100])
        return plan

    def _parse_plan(self, content: str) -> dict:
        """Parse the LLM response into a structured plan."""
        # Try to extract JSON from the response
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try to find JSON block in the response
        try:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(content[start:end])
        except json.JSONDecodeError:
            pass

        # Fallback: treat as thinking with no actions
        return {
            "thinking": content,
            "actions": [],
            "goals_update": None,
            "status_message": "Processing...",
        }
