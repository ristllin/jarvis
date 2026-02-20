import httpx

from jarvis.config import settings
from jarvis.tools.base import Tool, ToolResult

TELEGRAM_API = "https://api.telegram.org"


class SendTelegramTool(Tool):
    name = "send_telegram"
    description = "Sends a message via Telegram Bot API. Supports plain text and Markdown formatting."
    timeout_seconds = 15

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "message": {
                    "type": "string",
                    "description": "Message text (supports Markdown)",
                },
                "chat_id": {
                    "type": "string",
                    "description": "Target chat ID (optional — defaults to creator's chat)",
                },
                "parse_mode": {
                    "type": "string",
                    "description": "Formatting: 'Markdown', 'MarkdownV2', or 'HTML'",
                },
            },
            "required": ["message"],
        }

    async def execute(self, message: str = "", chat_id: str = "", parse_mode: str = "Markdown", **kwargs) -> ToolResult:
        if not message:
            return ToolResult(success=False, output="", error="Missing 'message' parameter")

        token = settings.telegram_bot_token
        if not token:
            return ToolResult(
                success=False,
                output="",
                error="TELEGRAM_BOT_TOKEN not configured. Set it in the environment or .env file.",
            )

        target_chat = chat_id or settings.telegram_chat_id
        if not target_chat:
            return ToolResult(
                success=False, output="", error="No chat_id provided and TELEGRAM_CHAT_ID not configured."
            )

        url = f"{TELEGRAM_API}/bot{token}/sendMessage"
        payload = {
            "chat_id": target_chat,
            "text": message,
            "parse_mode": parse_mode,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.post(url, json=payload)
                data = resp.json()

            if not data.get("ok"):
                err_desc = data.get("description", "Unknown Telegram API error")
                err_code = data.get("error_code", resp.status_code)
                return ToolResult(success=False, output="", error=f"Telegram API error {err_code}: {err_desc}")

            msg_id = data.get("result", {}).get("message_id", "?")
            return ToolResult(
                success=True,
                output=f"Message sent to chat {target_chat} (message_id: {msg_id})",
                error=None,
            )
        except httpx.TimeoutException:
            return ToolResult(success=False, output="", error="Telegram API request timed out")
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Failed to send Telegram message: {e}")
