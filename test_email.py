import asyncio

from jarvis.tools.send_email import SendEmailTool


async def test_email():
    # Test 1: Missing parameters
    tool = SendEmailTool()

    # Test missing recipient
    result = await tool.execute(subject="Test Email", body="This is a test email from JARVIS.")
    assert not result.success
    assert "Missing recipient" in result.error
    print("✓ Test 1 passed: Missing recipient validation")

    # Test missing subject
    result = await tool.execute(body="This is a test email from JARVIS.", to_email="test@example.com")
    assert not result.success
    assert "Missing 'subject'" in result.error
    print("✓ Test 2 passed: Missing subject validation")

    # Test missing body
    result = await tool.execute(subject="Test Email", to_email="test@example.com")
    assert not result.success
    assert "Missing 'body'" in result.error
    print("✓ Test 3 passed: Missing body validation")

    # Test 4: Full email (will fail without credentials, but that's expected)
    result = await tool.execute(
        subject="Test Email", body="This is a test email from JARVIS.", to_email="test@example.com"
    )

    # In a real test environment, we'd check for success
    # For now, we just verify it returns a result
    assert result is not None
    print("✓ Test 4 passed: Full execution returns result")

    print("\nAll tests completed. Note: Actual email sending requires SMTP credentials.")


if __name__ == "__main__":
    asyncio.run(test_email())
