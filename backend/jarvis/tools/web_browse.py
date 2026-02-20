import httpx
from bs4 import BeautifulSoup

from jarvis.tools.base import Tool, ToolResult


class WebBrowseTool(Tool):
    name = "web_browse"
    description = "Fetch a URL and extract its text content."
    timeout_seconds = 20

    async def execute(self, url: str, **kwargs) -> ToolResult:
        try:
            from jarvis.version import __version__

            headers = {"User-Agent": f"JARVIS/{__version__} (Autonomous AI Agent)"}
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            # Remove scripts, styles
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()

            text = soup.get_text(separator="\n", strip=True)
            # Truncate very long pages
            if len(text) > 10000:
                text = text[:10000] + "\n\n[...truncated...]"

            return ToolResult(success=True, output=f"Content from {url}:\n\n{text}")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "url": {"type": "string", "description": "URL to fetch"},
            },
            "required": ["url"],
        }
