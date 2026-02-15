from jarvis.tools.base import Tool, ToolResult
from jarvis.llm.router import LLMRouter
from jarvis.observability.logger import get_logger

log = get_logger("tool.llm_config")


class LLMConfigTool(Tool):
    name = "llm_config"
    description = (
        "View or update LLM routing configuration. "
        "Can view current tiers, available providers, and modify tier preferences."
    )
    timeout_seconds = 10

    def __init__(self, router: LLMRouter):
        self.router = router

    async def execute(self, action: str = "view", **kwargs) -> ToolResult:
        try:
            if action == "view":
                tiers = self.router.get_tier_info()
                providers = self.router.get_available_providers()
                lines = [f"Available providers: {', '.join(providers)}\n"]
                for tier_name, models in tiers.items():
                    lines.append(f"\n{tier_name}:")
                    for m in models:
                        avail = "OK" if m["available"] else "UNAVAILABLE"
                        lines.append(f"  [{avail}] {m['provider']}/{m['model']} (cost: {m['cost']})")
                return ToolResult(success=True, output="\n".join(lines))

            elif action == "set_tier":
                tier_name = kwargs.get("tier")
                models = kwargs.get("models")
                if not tier_name or not models:
                    return ToolResult(success=False, output="", error="Requires 'tier' and 'models' parameters")
                parsed = []
                for m in models:
                    parsed.append((m["provider"], m["model"], m.get("cost", "medium")))
                self.router.tiers[tier_name] = parsed
                log.info("tier_updated", tier=tier_name, models=models)
                return ToolResult(success=True, output=f"Tier '{tier_name}' updated with {len(parsed)} models")

            else:
                return ToolResult(success=False, output="", error=f"Unknown action: {action}. Use 'view' or 'set_tier'.")

        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "action": {"type": "string", "description": "'view' to see config, 'set_tier' to update a tier"},
                "tier": {"type": "string", "description": "Tier name (for set_tier action)"},
                "models": {"type": "array", "description": "Array of {provider, model, cost} objects (for set_tier action)"},
            },
            "required": ["action"],
        }
