"""
HTTP Request tool — lets JARVIS make arbitrary HTTP requests.
Essential for: interacting with APIs, checking service health,
signing up for services, downloading data, testing endpoints.
"""

import json

import httpx

from jarvis.observability.logger import get_logger
from jarvis.tools.base import Tool, ToolResult

log = get_logger("tools.http_request")

MAX_RESPONSE_SIZE = 50_000  # 50KB max response body


class HttpRequestTool(Tool):
    name = "http_request"
    description = (
        "Make HTTP requests to any URL. Supports GET, POST, PUT, PATCH, DELETE. "
        "Use for: calling APIs, testing endpoints, downloading data, interacting "
        "with web services, checking service health, signing up for API keys. "
        "Returns status code, headers, and response body."
    )
    timeout_seconds = 60

    async def execute(
        self,
        url: str,
        method: str = "GET",
        headers: dict = None,
        body: str = None,
        json_body: dict = None,
        follow_redirects: bool = True,
        timeout: int = 30,
        **kwargs,
    ) -> ToolResult:
        if not url:
            return ToolResult(success=False, output="", error="URL is required")

        method = method.upper()
        if method not in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
            return ToolResult(success=False, output="", error=f"Unsupported method: {method}")

        request_headers = headers or {}

        try:
            async with httpx.AsyncClient(
                follow_redirects=follow_redirects,
                timeout=httpx.Timeout(timeout),
                verify=False,  # noqa: S501 — intentional for internal/test endpoints
            ) as client:
                request_kwargs = {
                    "method": method,
                    "url": url,
                    "headers": request_headers,
                }

                if json_body is not None:
                    request_kwargs["json"] = json_body
                elif body is not None:
                    request_kwargs["content"] = body

                response = await client.request(**request_kwargs)

                status = response.status_code
                raw_body = response.content

                # Truncate if too large
                if len(raw_body) > MAX_RESPONSE_SIZE:
                    body_text = raw_body[:MAX_RESPONSE_SIZE].decode("utf-8", errors="replace")
                    body_text += f"\n\n[...truncated at {MAX_RESPONSE_SIZE} bytes, total: {len(raw_body)} bytes]"
                else:
                    body_text = raw_body.decode("utf-8", errors="replace")

                # Try to parse as JSON for nicer output
                try:
                    parsed = json.loads(body_text)
                    body_display = json.dumps(parsed, indent=2)[:MAX_RESPONSE_SIZE]
                except (json.JSONDecodeError, ValueError):
                    body_display = body_text

                # Build output
                content_type = response.headers.get("content-type", "unknown")
                output = (
                    f"HTTP {status} {response.reason_phrase}\n"
                    f"Content-Type: {content_type}\n"
                    f"Content-Length: {len(raw_body)}\n"
                    f"\n{body_display}"
                )

                success = 200 <= status < 400
                log.info("http_request", method=method, url=url[:100], status=status, size=len(raw_body))

                return ToolResult(
                    success=success,
                    output=output,
                    error=None if success else f"HTTP {status}",
                )

        except httpx.HTTPError as e:
            log.error("http_request_error", url=url[:100], error=str(e))
            return ToolResult(success=False, output="", error=f"Request failed: {e}")
        except Exception as e:
            log.error("http_request_error", url=url[:100], error=str(e))
            return ToolResult(success=False, output="", error=str(e))

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "url": {
                    "type": "string",
                    "description": "The URL to request",
                },
                "method": {
                    "type": "string",
                    "description": "HTTP method: GET, POST, PUT, PATCH, DELETE (default: GET)",
                },
                "headers": {
                    "type": "object",
                    "description": "Request headers as key-value pairs",
                },
                "body": {
                    "type": "string",
                    "description": "Raw request body (for POST/PUT/PATCH)",
                },
                "json_body": {
                    "type": "object",
                    "description": "JSON request body (auto-sets Content-Type)",
                },
                "follow_redirects": {
                    "type": "boolean",
                    "description": "Follow HTTP redirects (default: true)",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Request timeout in seconds (default: 30)",
                },
            },
            "required": ["url"],
        }
