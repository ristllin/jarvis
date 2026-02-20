"""
browser_agent tool — JARVIS's main agent calls this to spawn a browser subagent
that performs complex web automation tasks using Playwright.

The main agent provides:
  - task: what to do in the browser
  - start_url (optional): URL to navigate to initially
  - system_prompt (optional): custom instructions for the subagent
  - tier (optional): LLM tier to use (default: coding_level2)
  - max_turns (optional): max browser action iterations (default: 30)
  - headless (optional): run browser headless (default: true)
  - viewport (optional): browser viewport size
  - cookies (optional): cookies to set before starting
  - headers (optional): extra HTTP headers
  - continuation_context (optional): resume a previous session
"""
import json
from jarvis.tools.base import Tool, ToolResult
from jarvis.agents.browser_agent import BrowserAgent
from jarvis.observability.logger import get_logger

log = get_logger("tools.browser_agent")


class BrowserAgentTool(Tool):
    name = "browser_agent"
    description = (
        "Spawn a browser automation subagent to perform complex web tasks. "
        "The subagent controls a real Chromium browser via Playwright and can "
        "navigate pages, click elements, fill forms, extract data, take "
        "screenshots, run JavaScript, and more. Use this for web scraping, "
        "form filling, testing web apps, monitoring websites, or any task "
        "that requires browser interaction beyond simple HTTP requests."
    )
    timeout_seconds = 600  # 10 minutes

    def __init__(self, llm_router, blob_storage=None):
        self._agent = BrowserAgent(llm_router, blob_storage)

    async def execute(
        self,
        task: str,
        start_url: str = None,
        system_prompt: str = None,
        tier: str = "coding_level2",
        max_turns: int = 30,
        headless: bool = True,
        viewport: dict = None,
        cookies: list = None,
        headers: dict = None,
        continuation_context: list = None,
        **kwargs,
    ) -> ToolResult:
        try:
            result = await self._agent.run(
                task=task,
                start_url=start_url,
                system_prompt=system_prompt,
                tier=tier,
                max_turns=max_turns,
                headless=headless,
                viewport=viewport,
                cookies=cookies,
                headers=headers,
                continuation_context=continuation_context,
            )

            output = json.dumps(result, indent=2)
            return ToolResult(
                success=result.get("success", False),
                output=output,
                error=None if result.get("success") else result.get("summary", "Browser agent failed"),
            )
        except Exception as e:
            log.error("browser_agent_tool_error", error=str(e))
            return ToolResult(success=False, output="", error=str(e))

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "task": {
                    "type": "string",
                    "description": (
                        "Detailed description of what to do in the browser. "
                        "Be specific about which pages to visit, what data to extract, "
                        "what forms to fill, etc."
                    ),
                },
                "start_url": {
                    "type": "string",
                    "description": "URL to navigate to before starting the task.",
                },
                "system_prompt": {
                    "type": "string",
                    "description": (
                        "Optional custom instructions for the browser subagent. "
                        "Use to add context about the website, login credentials, etc."
                    ),
                },
                "tier": {
                    "type": "string",
                    "description": (
                        "LLM tier for the browser agent. Defaults to 'coding_level2' "
                        "(Devstral, free). Use 'coding_level1' for complex tasks."
                    ),
                },
                "max_turns": {
                    "type": "integer",
                    "description": "Maximum browser action iterations (default: 30).",
                },
                "headless": {
                    "type": "boolean",
                    "description": "Run browser in headless mode (default: true).",
                },
                "viewport": {
                    "type": "object",
                    "description": 'Browser viewport size, e.g. {"width": 1280, "height": 720}.',
                },
                "cookies": {
                    "type": "array",
                    "description": "Cookies to set before starting (list of cookie objects).",
                },
                "headers": {
                    "type": "object",
                    "description": "Extra HTTP headers to send with requests.",
                },
                "continuation_context": {
                    "type": "array",
                    "description": (
                        "Resume a previous browser session. Pass the 'continuation_context' "
                        "from a previous result that hit max_turns."
                    ),
                },
            },
            "required": ["task"],
        }
