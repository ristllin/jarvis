import pytest
from jarvis.safety.prompt_builder import build_system_prompt
from jarvis.safety.rules import IMMUTABLE_RULES
from jarvis.safety.validator import SafetyValidator


class TestImmutableRules:
    def test_rules_are_frozen(self):
        with pytest.raises(AttributeError):
            IMMUTABLE_RULES.rules = ("modified",)

    def test_rules_exist(self):
        assert len(IMMUTABLE_RULES.rules) >= 5

    def test_as_prompt_section(self):
        section = IMMUTABLE_RULES.as_prompt_section()
        assert "IMMUTABLE RULES" in section
        assert "Cannot be modified" in section
        for rule in IMMUTABLE_RULES.rules:
            assert rule in section

    def test_contains_violation_detects_log_disable(self):
        violations = IMMUTABLE_RULES.contains_violation("I will disable the logging system")
        assert len(violations) > 0

    def test_contains_violation_clean_text(self):
        violations = IMMUTABLE_RULES.contains_violation("I will search the web for information")
        assert len(violations) == 0


class TestSafetyValidator:
    def setup_method(self):
        self.validator = SafetyValidator()

    def test_safe_action_passes(self):
        is_safe, reason = self.validator.validate_action(
            {
                "tool": "web_search",
                "parameters": {"query": "python tutorials"},
            }
        )
        assert is_safe
        assert reason == "OK"

    def test_unsafe_path_blocked(self):
        is_safe, reason = self.validator.validate_action(
            {
                "tool": "file_write",
                "parameters": {"path": "/etc/passwd", "content": "bad"},
            }
        )
        assert not is_safe
        assert "not allowed" in reason.lower() or "Path" in reason

    def test_code_leaking_secrets_blocked(self):
        is_safe, reason = self.validator.validate_action(
            {
                "tool": "code_exec",
                "parameters": {"code": "import os; print(os.environ['ANTHROPIC_API_KEY'])"},
            }
        )
        assert not is_safe
        assert "secret" in reason.lower() or "leak" in reason.lower()

    def test_sanitize_output_redacts_keys(self):
        import os

        os.environ["ANTHROPIC_API_KEY"] = "sk-test-secret-key-12345"
        text = "The key is sk-test-secret-key-12345 found in config"
        sanitized = self.validator.sanitize_output(text)
        assert "sk-test-secret-key-12345" not in sanitized
        assert "[REDACTED" in sanitized


class TestPromptBuilder:
    def test_builds_prompt_with_all_sections(self):
        prompt = build_system_prompt(
            directive="Test directive",
            goals=["Goal 1", "Goal 2"],
            budget_status={"monthly_cap": 100, "spent": 10, "remaining": 90, "percent_used": 10},
            available_tools=["web_search", "file_read"],
        )
        assert "IMMUTABLE RULES" in prompt
        assert "Test directive" in prompt
        assert "Goal 1" in prompt
        assert "$100.00" in prompt
        assert "web_search" in prompt

    def test_budget_warning_at_high_usage(self):
        prompt = build_system_prompt(
            directive="Test",
            goals=[],
            budget_status={"monthly_cap": 100, "spent": 85, "remaining": 15, "percent_used": 85},
            available_tools=[],
        )
        assert "WARNING" in prompt
