"""
Environment Manager tool — lets JARVIS inspect and update its own
environment variables and .env file. Essential for adding new API keys,
configuring services, and self-management.
"""

import os

from jarvis.observability.logger import get_logger
from jarvis.tools.base import Tool, ToolResult

log = get_logger("tools.env_manager")

ENV_FILE = "/data/code/.env"
ENV_FILE_FALLBACK = "/app/.env"

# Keys that MUST NOT be exposed or modified (security)
PROTECTED_KEYS = {
    "GMAIL_USER_PASSWORD",
}

# Keys that can be read (showing value) vs sensitive (showing masked)
SENSITIVE_PREFIXES = ("PASSWORD", "SECRET", "TOKEN", "KEY")


def _is_sensitive(key: str) -> bool:
    upper = key.upper()
    return any(p in upper for p in SENSITIVE_PREFIXES)


def _mask(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return value[:4] + "..." + value[-4:]


def _find_env_file() -> str:
    if os.path.isfile(ENV_FILE):
        return ENV_FILE
    if os.path.isfile(ENV_FILE_FALLBACK):
        return ENV_FILE_FALLBACK
    return ENV_FILE


class EnvManagerTool(Tool):
    name = "env_manager"
    description = (
        "Inspect and update environment variables and the .env configuration file. "
        "Actions: 'list' (show all env vars), 'get' (read a specific var), "
        "'set' (update or add an env var — writes to .env file and live environment), "
        "'delete' (remove an env var). "
        "Use this to add new API keys, configure services, and manage credentials. "
        "Note: changes to .env take full effect after container restart."
    )
    timeout_seconds = 10

    async def execute(
        self,
        action: str = "list",
        key: str = None,
        value: str = None,
        **kwargs,
    ) -> ToolResult:
        action = action.lower().strip()

        if action == "list":
            return self._list_env()
        if action == "get":
            return self._get_env(key)
        if action == "set":
            return self._set_env(key, value)
        if action == "delete":
            return self._delete_env(key)
        return ToolResult(
            success=False,
            output="",
            error=f"Unknown action: {action}. Use: list, get, set, delete",
        )

    def _list_env(self) -> ToolResult:
        """List all relevant env vars (masks sensitive values)."""
        relevant = {}
        for k, v in sorted(os.environ.items()):
            if k.startswith(
                (
                    "JARVIS",
                    "GMAIL",
                    "ANTHROPIC",
                    "OPENAI",
                    "MISTRAL",
                    "TAVILY",
                    "GITHUB",
                    "SMTP",
                    "EMAIL",
                    "MONTHLY",
                    "DATA_DIR",
                    "OLLAMA",
                    "GIT_",
                )
            ):
                if k in PROTECTED_KEYS:
                    continue
                relevant[k] = _mask(v) if _is_sensitive(k) else v

        lines = [f"{len(relevant)} environment variables:"]
        for k, v in relevant.items():
            lines.append(f"  {k}={v}")

        # Also show .env file contents
        env_file = _find_env_file()
        if os.path.isfile(env_file):
            lines.append(f"\n.env file ({env_file}):")
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        lines.append(f"  {line}")
                        continue
                    if "=" in line:
                        ek, ev = line.split("=", 1)
                        if ek.strip() in PROTECTED_KEYS:
                            continue
                        if _is_sensitive(ek.strip()):
                            lines.append(f"  {ek.strip()}={_mask(ev.strip())}")
                        else:
                            lines.append(f"  {line}")
                    else:
                        lines.append(f"  {line}")

        return ToolResult(success=True, output="\n".join(lines))

    def _get_env(self, key: str) -> ToolResult:
        if not key:
            return ToolResult(success=False, output="", error="Key is required")
        if key.upper() in PROTECTED_KEYS:
            return ToolResult(success=False, output="", error=f"Cannot read protected key: {key}")

        value = os.environ.get(key) or os.environ.get(key.upper())
        if value is None:
            return ToolResult(success=False, output="", error=f"Variable {key} not found")

        display = _mask(value) if _is_sensitive(key) else value
        return ToolResult(
            success=True,
            output=f"{key}={display}\n(length: {len(value)} chars, is set: True)",
        )

    def _set_env(self, key: str, value: str) -> ToolResult:
        if not key or value is None:
            return ToolResult(success=False, output="", error="Both key and value are required")
        if key.upper() in PROTECTED_KEYS:
            return ToolResult(success=False, output="", error=f"Cannot modify protected key: {key}")

        key = key.upper()

        # Set in live environment
        os.environ[key] = value
        log.info("env_set_live", key=key)

        # Update .env file
        env_file = _find_env_file()
        try:
            lines = []
            found = False
            if os.path.isfile(env_file):
                with open(env_file) as f:
                    for line in f:
                        stripped = line.strip()
                        if stripped and not stripped.startswith("#") and "=" in stripped:
                            ek = stripped.split("=", 1)[0].strip()
                            if ek.upper() == key:
                                lines.append(f"{key}={value}\n")
                                found = True
                                continue
                        lines.append(line)

            if not found:
                lines.append(f"{key}={value}\n")

            with open(env_file, "w") as f:
                f.writelines(lines)

            log.info("env_set_file", key=key, file=env_file)
            display = _mask(value) if _is_sensitive(key) else value
            return ToolResult(
                success=True,
                output=(
                    f"Set {key}={display}\n"
                    f"Updated in: live environment + {env_file}\n"
                    f"Note: some settings require container restart to take effect."
                ),
            )
        except Exception as e:
            return ToolResult(
                success=True,
                output=f"Set {key} in live environment, but failed to write .env: {e}",
            )

    def _delete_env(self, key: str) -> ToolResult:
        if not key:
            return ToolResult(success=False, output="", error="Key is required")
        if key.upper() in PROTECTED_KEYS:
            return ToolResult(success=False, output="", error=f"Cannot delete protected key: {key}")

        key = key.upper()

        # Remove from live env
        removed_live = key in os.environ
        if removed_live:
            del os.environ[key]

        # Remove from .env file
        env_file = _find_env_file()
        removed_file = False
        if os.path.isfile(env_file):
            try:
                lines = []
                with open(env_file) as f:
                    for line in f:
                        stripped = line.strip()
                        if stripped and not stripped.startswith("#") and "=" in stripped:
                            ek = stripped.split("=", 1)[0].strip()
                            if ek.upper() == key:
                                removed_file = True
                                continue
                        lines.append(line)
                with open(env_file, "w") as f:
                    f.writelines(lines)
            except Exception as e:
                return ToolResult(
                    success=True,
                    output=f"Removed {key} from live environment, but failed to update .env: {e}",
                )

        if removed_live or removed_file:
            return ToolResult(
                success=True,
                output=f"Removed {key} (live: {removed_live}, .env: {removed_file})",
            )
        return ToolResult(success=False, output="", error=f"Variable {key} not found")

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "action": {
                    "type": "string",
                    "description": "One of: list, get, set, delete",
                    "enum": ["list", "get", "set", "delete"],
                },
                "key": {
                    "type": "string",
                    "description": "Environment variable name (e.g. 'MISTRAL_API_KEY')",
                },
                "value": {
                    "type": "string",
                    "description": "Value to set (for 'set' action)",
                },
            },
            "required": ["action"],
        }
