from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from jarvis.tools.send_telegram import SendTelegramTool


@pytest.mark.asyncio
class TestSendTelegramTool:
    async def test_missing_message(self):
        tool = SendTelegramTool()
        result = await tool.execute(message="")
        assert not result.success
        assert "Missing 'message'" in result.error

    async def test_missing_token(self):
        tool = SendTelegramTool()
        with patch("jarvis.tools.send_telegram.settings") as mock_s:
            mock_s.telegram_bot_token = None
            mock_s.telegram_chat_id = "123"
            result = await tool.execute(message="Hello")
            assert not result.success
            assert "TELEGRAM_BOT_TOKEN" in result.error

    async def test_missing_chat_id(self):
        tool = SendTelegramTool()
        with patch("jarvis.tools.send_telegram.settings") as mock_s:
            mock_s.telegram_bot_token = "fake-token"
            mock_s.telegram_chat_id = None
            result = await tool.execute(message="Hello")
            assert not result.success
            assert "chat_id" in result.error

    async def test_successful_send(self):
        tool = SendTelegramTool()
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True, "result": {"message_id": 42}}

        with patch("jarvis.tools.send_telegram.settings") as mock_s:
            mock_s.telegram_bot_token = "fake-token"
            mock_s.telegram_chat_id = "123456"
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client_cls.return_value = mock_client

                result = await tool.execute(message="Hello from JARVIS")
                assert result.success
                assert "42" in result.output

    async def test_api_error(self):
        tool = SendTelegramTool()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"ok": False, "error_code": 401, "description": "Unauthorized"}

        with patch("jarvis.tools.send_telegram.settings") as mock_s:
            mock_s.telegram_bot_token = "bad-token"
            mock_s.telegram_chat_id = "123"
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client_cls.return_value = mock_client

                result = await tool.execute(message="test")
                assert not result.success
                assert "401" in result.error

    def test_schema(self):
        tool = SendTelegramTool()
        schema = tool.get_schema()
        assert schema["name"] == "send_telegram"
        assert "message" in schema["parameters"]
        assert "message" in schema["required"]
