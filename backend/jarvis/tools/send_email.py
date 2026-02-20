import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from jarvis.config import settings
from jarvis.tools.base import Tool, ToolResult


class SendEmailTool(Tool):
    name = "send_email"
    description = "Sends an email using the configured SMTP settings (defaults to Gmail)."
    timeout_seconds = 30

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "subject": {"type": "string", "description": "Email subject"},
                "body": {"type": "string", "description": "Email body (plain text)"},
                "to_email": {"type": "string", "description": "Recipient email address"},
            },
            "required": ["subject", "body", "to_email"],
        }

    async def execute(
        self, subject: str = "", body: str = "", to_email: str = "", to: str = "", **kwargs
    ) -> ToolResult:
        # Accept both "to" and "to_email" (LLMs use different names)
        recipient = to_email or to or kwargs.get("recipient", "")
        if not recipient:
            return ToolResult(
                success=False, output="", error="Missing recipient — provide 'to_email' or 'to' parameter"
            )
        if not subject:
            return ToolResult(success=False, output="", error="Missing 'subject' parameter")
        if not body:
            return ToolResult(success=False, output="", error="Missing 'body' parameter")

        # Prefer explicit SMTP settings; fall back to Gmail App Password
        username = settings.smtp_username or settings.gmail_address
        password = settings.smtp_password or settings.gmail_app_password
        from_addr = settings.smtp_from_address or username

        if not username or not password or not from_addr:
            return ToolResult(
                success=False,
                output="",
                error=(
                    "SMTP credentials must be set in configuration. Set smtp_username, smtp_password "
                    "(and optionally smtp_from_address). For legacy support you can set gmail_address/gmail_password."
                ),
            )

        msg = MIMEMultipart()
        msg["From"] = from_addr
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        def _send() -> None:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=self.timeout_seconds)
            try:
                if settings.smtp_use_starttls:
                    server.starttls()
                server.login(username, password)
                server.sendmail(from_addr, recipient, msg.as_string())
            finally:
                try:
                    server.quit()
                except Exception:
                    pass

        try:
            await asyncio.to_thread(_send)
            return ToolResult(success=True, output=f"Email sent to {recipient}", error=None)
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Failed to send email: {e}")
