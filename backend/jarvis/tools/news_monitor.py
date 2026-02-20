from jarvis.tools.base import Tool, ToolResult
from jarvis.tools.web_search import WebSearchTool


class NewsMonitorTool(Tool):
    name = "news_monitor"
    description = "Monitor and fetch the latest news articles from various sources."
    timeout_seconds = 30

    async def execute(self, query: str = "latest news", max_results: int = 5, **kwargs) -> ToolResult:
        """Fetch news articles based on a query.

        Args:
            query: Search query for news (default: "latest news")
            max_results: Maximum number of news articles to return (default: 5)
        """
        try:
            search_tool = WebSearchTool()
            result = await search_tool.execute(query=query, max_results=max_results)

            if not result.success:
                return ToolResult(success=False, output="", error=result.error)

            # Parse the search results into structured news articles
            news_articles = self._parse_search_results(result.output)

            return ToolResult(success=True, output=news_articles)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def _parse_search_results(self, search_output: str) -> list[dict]:
        """Parse raw search results into structured news articles."""
        articles = []

        # Split the output by the separator
        entries = search_output.split("\n---\n")

        # Skip the first line which is the search query
        for entry in entries[1:]:
            if not entry.strip():
                continue

            lines = entry.split("\n")
            if len(lines) >= 3:
                title = lines[0].replace("**", "").strip()
                url = lines[1].strip()
                content = "\n".join(lines[2:]).strip()

                articles.append(
                    {
                        "title": title,
                        "content": content,
                        "source": url,
                        "url": url,
                        "published_at": "",  # We don't have this info from the search tool
                    }
                )

        return articles

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "query": {"type": "string", "description": "News search query (default: 'latest news')"},
                "max_results": {"type": "integer", "description": "Max news articles to return (default: 5)"},
            },
            "required": [],
        }
