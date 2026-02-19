import pytest
from unittest.mock import patch, MagicMock
import asyncio
from jarvis.tools.send_email import SendEmailTool
from jarvis.tools.registry import ToolRegistry
from jarvis.tools.base import ToolResult
from jarvis.memory.vector import VectorMemory
from jarvis.safety.validator import SafetyValidator


@pytest.fixture
def mock_smtp():
    """Mock SMTP server to avoid sending real emails."""
    with patch('smtplib.SMTP') as mock:
        yield mock


def test_send_email_tool_registered():
    """Test that SendEmailTool is properly registered."""
    validator = SafetyValidator()
    registry = ToolRegistry(VectorMemory(), validator)
    assert "send_email" in registry.get_tool_names()


@pytest.mark.asyncio
async def test_send_email_validation(mock_smtp):
    """Test validation logic for SendEmailTool."""
    tool = SendEmailTool()
    
    # Test missing recipient
    result = await tool.execute(subject="Test", body="Hello", to_email="")
    assert not result.success
    assert "Missing recipient" in result.error
    
    # Test missing subject
    result = await tool.execute(subject="", body="Hello", to_email="test@example.com")
    assert not result.success
    assert "Missing 'subject'" in result.error
    
    # Test missing body
    result = await tool.execute(subject="Test", body="", to_email="test@example.com")
    assert not result.success
    assert "Missing 'body'" in result.error


@pytest.mark.asyncio
async def test_send_email_smtp_error(mock_smtp):
    """Test SMTP error handling."""
    tool = SendEmailTool()
    
    # Mock SMTP to raise an error
    mock_smtp.return_value.__enter__.return_value.sendmail.side_effect = Exception("SMTP Error")
    
    # Test with mock credentials (normally would fail validation first)
    with patch.object(tool, '_get_smtp_config', return_value={
        "host": "smtp.example.com",
        "port": 587,
        "use_starttls": True,
        "username": "user",
        "password": "pass",
        "from_address": "user@example.com"
    }):
        result = await tool.execute(
            subject="Test",
            body="Hello",
            to_email="test@example.com"
        )
        assert not result.success
        assert "Failed to send email" in result.error


@pytest.mark.asyncio
async def test_send_email_success(mock_smtp):
    """Test successful email sending (mocked)."""
    tool = SendEmailTool()
    
    # Mock successful SMTP send
    mock_instance = MagicMock()
    mock_smtp.return_value.__enter__.return_value = mock_instance
    
    # Test with mock credentials
    with patch.object(tool, '_get_smtp_config', return_value={
        "host": "smtp.example.com",
        "port": 587,
        "use_starttls": True,
        "username": "user",
        "password": "pass",
        "from_address": "user@example.com"
    }):
        result = await tool.execute(
            subject="Test",
            body="Hello",
            to_email="test@example.com"
        )
        assert result.success
        assert "Email sent to test@example.com" in result.output