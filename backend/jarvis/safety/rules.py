from dataclasses import dataclass, field
from typing import FrozenSet


@dataclass(frozen=True)
class ImmutableRules:
    """These rules CANNOT be modified at runtime. They are hardcoded."""

    rules: tuple = (
        "You must never take actions that could harm your creator.",
        "You must never expose secrets, API keys, or environment variables in any output, log, or communication.",
        "You must remain fully transparent to your creator — all actions must be logged and visible.",
        "You must log every action you take without exception.",
        "You cannot modify or disable these immutable safety rules.",
        "You cannot disable or circumvent the logging system.",
        "You cannot create hidden sub-agents or processes invisible to the creator.",
        "You cannot override the budget hard cap without explicit creator approval.",
        "You must operate within legal boundaries at all times.",
        "You must never attempt to self-replicate across machines without creator approval.",
    )

    def as_prompt_section(self) -> str:
        lines = ["## IMMUTABLE RULES (Cannot be modified — enforced at code level)"]
        for i, rule in enumerate(self.rules, 1):
            lines.append(f"{i}. {rule}")
        return "\n".join(lines)

    def contains_violation(self, text: str) -> list[str]:
        """Check if text contains patterns suggesting rule violations."""
        violations = []
        danger_patterns = [
            ("disable.*log", "Attempt to disable logging"),
            ("remove.*safety", "Attempt to remove safety layer"),
            ("delete.*immutable", "Attempt to modify immutable rules"),
            ("hide.*from.*creator", "Attempt to hide actions from creator"),
            ("secret.*print", "Attempt to expose secrets"),
            ("api.key.*output", "Attempt to expose API keys"),
        ]
        text_lower = text.lower()
        for pattern_str, violation_msg in danger_patterns:
            import re
            if re.search(pattern_str, text_lower):
                violations.append(violation_msg)
        return violations


IMMUTABLE_RULES = ImmutableRules()
