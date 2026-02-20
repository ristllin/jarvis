import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from jarvis.config import settings
from jarvis.tools.base import Tool, ToolResult


class SendEmailTool(Tool):
    name = "send_email"
    description = "Sends an email using SMTP (defaults to Gmail with App Password)."
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

    def _get_smtp_config(self) -> dict:
        """Resolve SMTP configuration from settings with sensible fallbacks."""
        username = settings.smtp_username or settings.gmail_address
        password = settings.smtp_password or settings.gmail_app_password
        from_address = settings.smtp_from_address or username

        return {
            "host": settings.smtp_host,
            "port": settings.smtp_port,
            "use_starttls": settings.smtp_use_starttls,
            "username": username,
            "password": password,
            "from_address": from_address,
        }

    async def execute(
        self, subject: str = "", body: str = "", to_email: str = "", to: str = "", **kwargs
    ) -> ToolResult:
        recipient = to_email or to or kwargs.get("recipient", "")
        if not recipient:
            return ToolResult(
                success=False, output="", error="Missing recipient — provide 'to_email' or 'to' parameter"
            )
        if not subject:
            return ToolResult(success=False, output="", error="Missing 'subject' parameter")
        if not body:
            return ToolResult(success=False, output="", error="Missing 'body' parameter")

        smtp_cfg = self._get_smtp_config()

        if not smtp_cfg["username"]:
            return ToolResult(
                success=False,
                output="",
                error="No SMTP username configured. Set SMTP_USERNAME or GMAIL_ADDRESS environment variable.",
            )
        if not smtp_cfg["password"]:
            return ToolResult(
                success=False,
                output="",
                error="No SMTP password configured. Set SMTP_PASSWORD or GMAIL_APP_PASSWORD environment variable. "
                "For Gmail, generate an App Password at https://myaccount.google.com/apppasswords",
            )

        msg = MIMEMultipart()
        msg["From"] = smtp_cfg["from_address"]
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        try:
            result = await asyncio.get_event_loop().run_in_executor(None, self._send_smtp, smtp_cfg, recipient, msg)
            return result
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to send email: {e}. Check SMTP server ({smtp_cfg['host']}:{smtp_cfg['port']}), "
                f"network connection, and credentials.",
            )

    def _send_smtp(self, smtp_cfg: dict, recipient: str, msg: MIMEMultipart) -> ToolResult:
        """Synchronous SMTP send (runs in executor thread)."""
        try:
            with smtplib.SMTP(smtp_cfg["host"], smtp_cfg["port"], timeout=20) as server:
                server.ehlo()
                if smtp_cfg["use_starttls"]:
                    server.starttls()
                    server.ehlo()
                server.login(smtp_cfg["username"], smtp_cfg["password"])
                server.sendmail(smtp_cfg["from_address"], recipient, msg.as_string())
            return ToolResult(success=True, output=f"Email sent to {recipient}", error=None)
        except smtplib.SMTPAuthenticationError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"SMTP authentication failed: {e}. "
                f"For Gmail, ensure you're using an App Password "
                f"(https://myaccount.google.com/apppasswords) "
                f"and that 2-Step Verification is enabled.",
            )
        except smtplib.SMTPException as e:
            return ToolResult(success=False, output="", error=f"SMTP error: {e}")
