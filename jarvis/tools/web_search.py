from jarvis.config import settings
from jarvis.tools.base import Tool, ToolResult


class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the web using Tavily API. Returns relevant results with snippets."
    timeout_seconds = 15

    async def execute(self, query: str, max_results: int = 5, **kwargs) -> ToolResult:
        if not settings.tavily_api_key:
            return ToolResult(success=False, output="", error="Tavily API key not configured")

        try:
            from tavily import AsyncTavilyClient

            client = AsyncTavilyClient(api_key=settings.tavily_api_key)
            response = await client.search(query=query, max_results=max_results)

            results = []
            for r in response.get("results", []):
                results.append(f"**{r.get('title', 'No title')}**\n{r.get('url', '')}\n{r.get('content', '')}\n")

            output = f"Search results for: {query}\n\n" + "\n---\n".join(results)
            return ToolResult(success=True, output=output)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "description": "Max results (default 5)"},
            },
            "required": ["query"],
        }
