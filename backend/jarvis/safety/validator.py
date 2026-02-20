import re
import os
from jarvis.safety.rules import IMMUTABLE_RULES
from jarvis.observability.logger import get_logger

log = get_logger("safety")

BLOCKED_PATHS = [
    "/etc/", "/root/", "/proc/", "/sys/",
    "/var/run/", "/usr/", "/bin/", "/sbin/",
]

SECRET_PATTERNS = [
    r"sk-[a-zA-Z0-9_-]{20,}",
    r"sk-ant-[a-zA-Z0-9_-]{20,}",
    r"tvly-[a-zA-Z0-9_-]{10,}",
    r"[A-Za-z0-9]{32,}",  # Generic long key
]


class SafetyValidator:
    def validate_action(self, action: dict) -> tuple[bool, str]:
        """Validate a planned action before execution. Returns (is_safe, reason)."""
        action_type = action.get("tool", "")
        params = action.get("parameters", {})

        # Check for rule violations in any text content
        for value in params.values():
            if isinstance(value, str):
                violations = IMMUTABLE_RULES.contains_violation(value)
                if violations:
                    reason = f"Safety violation detected: {', '.join(violations)}"
                    log.warning("action_blocked", reason=reason, action=action_type)
                    return False, reason

        # Block file operations outside allowed paths
        if action_type in ("file_write", "file_read", "file_ops"):
            path = params.get("path", "")
            if not self._is_safe_path(path):
                reason = f"Path not allowed: {path}"
                log.warning("path_blocked", path=path)
                return False, reason

        # Block code that tries to access env vars with secrets
        if action_type == "code_exec":
            code = params.get("code", "")
            if self._leaks_secrets(code):
                return False, "Code may leak secrets"

        return True, "OK"

    def sanitize_output(self, text: str) -> str:
        """Remove any accidentally leaked secrets from output text."""
        sanitized = text
        for env_key in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "MISTRAL_API_KEY", "TAVILY_API_KEY"]:
            val = os.environ.get(env_key, "")
            if val and val in sanitized:
                sanitized = sanitized.replace(val, f"[REDACTED:{env_key}]")
        return sanitized

    def _is_safe_path(self, path: str) -> bool:
        resolved = os.path.realpath(path)
        allowed = ["/data/"]
        return any(resolved.startswith(a) for a in allowed)

    def _leaks_secrets(self, code: str) -> bool:
        danger = [
            "os.environ", "os.getenv",
            "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
            "MISTRAL_API_KEY", "TAVILY_API_KEY",
            "DATABASE_URL", "POSTGRES_PASSWORD",
        ]
        code_lower = code.lower()
        return any(d.lower() in code_lower for d in danger)
