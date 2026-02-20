from jarvis.memory.models import WorkingContext
from jarvis.observability.logger import get_logger

log = get_logger("working_memory")

# Rough token estimation: 1 token ~ 4 chars
MAX_CONTEXT_TOKENS = 120_000

# Default memory retrieval config
DEFAULT_MEMORY_CONFIG = {
    "retrieval_count": 10,           # How many vector memories to inject per iteration
    "max_context_tokens": 120_000,   # Max working context size in tokens
    "decay_factor": 0.95,            # Importance decay per maintenance cycle
    "relevance_threshold": 0.0,      # Min relevance score to include (0 = include all)
}


class WorkingMemory:
    """Manages the rolling context window for LLM calls."""

    def __init__(self):
        self.messages: list[dict] = []
        self.system_prompt: str = ""
        self.injected_memories: list[str] = []
        self.injected_memories_raw: list[dict] = []  # Full entries with metadata (for UI)
        self.memory_config: dict = dict(DEFAULT_MEMORY_CONFIG)

    def set_system_prompt(self, prompt: str):
        self.system_prompt = prompt

    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        self._trim_if_needed()

    def inject_memories(self, memories: list[str], raw_entries: list[dict] = None):
        self.injected_memories = memories
        self.injected_memories_raw = raw_entries or []

    def update_config(self, **kwargs):
        """Update memory config (retrieval count, thresholds, etc.)"""
        for key, value in kwargs.items():
            if key in self.memory_config:
                self.memory_config[key] = value
                log.info("memory_config_updated", key=key, value=value)

    def get_context(self) -> WorkingContext:
        return WorkingContext(
            system_prompt=self.system_prompt,
            recent_messages=list(self.messages),
            injected_memories=self.injected_memories,
            total_tokens_estimate=self._estimate_tokens(),
        )

    def get_working_snapshot(self) -> dict:
        """Get a snapshot of current working memory for the UI."""
        truncated_messages = []
        for msg in self.messages:
            truncated_messages.append(
                {
                    "role": msg.get("role", ""),
                    "content": msg.get("content", "")[:2000],
                    "full_length": len(msg.get("content", "")),
                }
            )

        sys_tokens = len(self.system_prompt) // 4
        mem_chars = sum(len(m) for m in self.injected_memories)
        mem_tokens = mem_chars // 4
        msg_chars = sum(len(m.get("content", "")) for m in self.messages)
        msg_tokens = msg_chars // 4

        # Build prompt_sections for the UI's PromptSectionsViewer
        prompt_sections = [
            {
                "name": "System Prompt",
                "description": "Directive, goals, tools, safety rules, and instructions",
                "content": self.system_prompt[:8000],
                "tokens": sys_tokens,
            },
        ]
        if self.injected_memories:
            mem_content = "\n".join(f"- {m[:500]}" for m in self.injected_memories[:20])
            prompt_sections.append(
                {
                    "name": "Injected Memories",
                    "description": f"{len(self.injected_memories)} vector memories retrieved by relevance",
                    "content": mem_content,
                    "tokens": mem_tokens,
                }
            )
        for i, msg in enumerate(self.messages[-10:]):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            idx = len(self.messages) - 10 + i if len(self.messages) > 10 else i
            prompt_sections.append(
                {
                    "name": f"Message #{idx} ({role})",
                    "description": f"{role} message, {len(content)} chars",
                    "content": content[:4000],
                    "tokens": len(content) // 4,
                }
            )

        return {
            "system_prompt_length": len(self.system_prompt),
            "system_prompt_tokens": sys_tokens,
            "message_count": len(self.messages),
            "injected_memory_count": len(self.injected_memories),
            "injected_memories": self.injected_memories_raw[:50],
            "total_tokens_estimate": self._estimate_tokens(),
            "max_context_tokens": self.memory_config["max_context_tokens"],
            "config": dict(self.memory_config),
            "token_breakdown": {
                "system_prompt": sys_tokens,
                "injected_memories": mem_tokens,
                "messages": msg_tokens,
            },
            "prompt_sections": prompt_sections,
        }

    def get_messages_for_llm(self) -> list[dict]:
        """Build the full message list for an LLM call."""
        messages = []

        # System prompt always first
        system_content = self.system_prompt
        if self.injected_memories:
            system_content += "\n\n## RELEVANT MEMORIES\n"
            for mem in self.injected_memories:
                system_content += f"- {mem}\n"

        messages.append({"role": "system", "content": system_content})
        messages.extend(self.messages)
        return messages

    def clear(self):
        self.messages = []
        self.injected_memories = []

    def summarize_and_compress(self, summary: str):
        """Replace old messages with a summary to free context space."""
        if len(self.messages) <= 2:
            return
        # Keep last 2 messages, replace rest with summary
        kept = self.messages[-2:]
        self.messages = [
            {"role": "system", "content": f"[Summary of prior conversation]: {summary}"},
            *kept,
        ]
        log.info("context_compressed", remaining_messages=len(self.messages))

    def _trim_if_needed(self):
        while self._estimate_tokens() > MAX_CONTEXT_TOKENS and len(self.messages) > 2:
            self.messages.pop(0)

    def _estimate_tokens(self) -> int:
        total_chars = len(self.system_prompt)
        for mem in self.injected_memories:
            total_chars += len(mem)
        for msg in self.messages:
            total_chars += len(msg.get("content", ""))
        return total_chars // 4
