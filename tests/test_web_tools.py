from unittest.mock import patch

import pytest
from jarvis.tools.http_request import HttpRequestTool
from jarvis.tools.web_browse import WebBrowseTool
from jarvis.tools.web_search import WebSearchTool


class TestWebSearchTool:
    def test_schema(self):
        tool = WebSearchTool()
        schema = tool.get_schema()
        assert schema["name"] == "web_search"
        assert "query" in schema.get("parameters", {})

    @pytest.mark.asyncio
    async def test_missing_query(self):
        tool = WebSearchTool()
        result = await tool.execute(query="")
        assert not result.success

    @pytest.mark.asyncio
    async def test_no_api_key(self):
        tool = WebSearchTool()
        with patch("jarvis.tools.web_search.settings") as mock_s:
            mock_s.tavily_api_key = None
            result = await tool.execute(query="test query")
            assert not result.success


class TestWebBrowseTool:
    def test_schema(self):
        tool = WebBrowseTool()
        schema = tool.get_schema()
        assert schema["name"] == "web_browse"
        assert "url" in schema.get("parameters", {})

    @pytest.mark.asyncio
    async def test_missing_url(self):
        tool = WebBrowseTool()
        result = await tool.execute(url="")
        assert not result.success

    @pytest.mark.asyncio
    async def test_invalid_url(self):
        tool = WebBrowseTool()
        result = await tool.execute(url="not-a-url")
        assert not result.success


class TestHttpRequestTool:
    def test_schema(self):
        tool = HttpRequestTool()
        schema = tool.get_schema()
        assert schema["name"] == "http_request"

    @pytest.mark.asyncio
    async def test_missing_url(self):
        tool = HttpRequestTool()
        result = await tool.execute(url="", method="GET")
        assert not result.success
