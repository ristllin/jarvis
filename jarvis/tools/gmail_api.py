import base64
import json
import os
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from jarvis.config import settings
from jarvis.tools.base import Tool, ToolResult


class GmailAPITool(Tool):
    name = "gmail_api"
    description = (
        "Interacts with Gmail API using OAuth2 authentication. "
        "NOTE: For simple email sending, prefer the 'send_email' tool which uses SMTP. "
        "This tool requires OAuth2 credentials (gmail_credentials.json + token) "
        "and is needed only for advanced Gmail operations like listing/reading messages."
    )
    timeout_seconds = 30

    # Scopes required for Gmail API
    SCOPES = ["https://www.googleapis.com/auth/gmail.send", "https://www.googleapis.com/auth/gmail.readonly"]

    def __init__(self):
        super().__init__()
        self._credentials = None
        self._service = None
        self._setup_status = ""
        self._load_credentials()

    def _ensure_credentials_file(self) -> str | None:
        """Ensure gmail_credentials.json exists.

        If GMAIL_OAUTH_CLIENT_JSON env var is set (containing the full JSON
        string from Google Cloud Console), write it to the expected path.
        Returns the path if the file exists, None otherwise.
        """
        credentials_path = os.path.join(settings.data_dir, "gmail_credentials.json")

        # If file already exists, use it
        if os.path.exists(credentials_path):
            return credentials_path

        # Try to create from environment variable
        oauth_json = os.environ.get("GMAIL_OAUTH_CLIENT_JSON", "")
        if oauth_json:
            try:
                # Validate it's proper JSON
                json.loads(oauth_json)
                with open(credentials_path, "w") as f:
                    f.write(oauth_json)
                return credentials_path
            except (OSError, json.JSONDecodeError) as e:
                self._setup_status = f"GMAIL_OAUTH_CLIENT_JSON env var is set but invalid: {e}"
                return None

        self._setup_status = (
            "Gmail OAuth2 credentials not found. To set up:\n"
            "1. Go to https://console.cloud.google.com/apis/credentials\n"
            "2. Create OAuth2 Client ID (Desktop application)\n"
            "3. Download the JSON file\n"
            "4. Either:\n"
            "   a. Place it at /data/gmail_credentials.json, OR\n"
            "   b. Set GMAIL_OAUTH_CLIENT_JSON env var with the file contents\n"
            "5. Run the OAuth2 flow once to generate a token\n\n"
            "For simple email sending, use the 'send_email' tool instead "
            "(uses SMTP with App Password, no OAuth2 needed)."
        )
        return None

    def _load_credentials(self):
        """Load or create OAuth2 credentials"""
        creds = None
        token_path = os.path.join(settings.data_dir, "gmail_token.json")

        # Check if token exists (previously authorized)
        if os.path.exists(token_path):
            try:
                creds = Credentials.from_authorized_user_file(token_path, self.SCOPES)
            except Exception as e:
                self._setup_status = f"Failed to load token: {e}"
                creds = None

        # If token is expired, try to refresh
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(token_path, "w") as token:
                    token.write(creds.to_json())
            except Exception as e:
                self._setup_status = f"Failed to refresh token: {e}"
                creds = None

        # If we have valid creds, build the service
        if creds and creds.valid:
            self._credentials = creds
            self._service = build("gmail", "v1", credentials=creds)
            self._setup_status = "Gmail API ready"
            return

        # No valid token — check if credentials file exists for future OAuth flow
        credentials_path = self._ensure_credentials_file()
        if not credentials_path:
            self._credentials = None
            self._service = None
            return

        # We have credentials.json but no valid token
        # NOTE: InstalledAppFlow.run_local_server() requires a browser,
        # which won't work in a headless container. Log instructions.
        self._setup_status = (
            "Gmail OAuth2 credentials file found but no valid token. "
            "The OAuth2 authorization flow requires a browser and cannot "
            "run in a headless container. To authorize:\n"
            "1. Run the OAuth2 flow on a machine with a browser\n"
            "2. Copy the resulting token file to /data/gmail_token.json\n\n"
            "For simple email sending, use the 'send_email' tool instead."
        )
        self._credentials = None
        self._service = None

    def _get_service(self) -> Any | None:
        """Ensure service is available"""
        if not self._service or not self._credentials:
            self._load_credentials()
        return self._service

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "action": {
                    "type": "string",
                    "description": "Action to perform: send_email, list_messages, get_message",
                    "enum": ["send_email", "list_messages", "get_message"],
                },
                "subject": {"type": "string", "description": "Email subject (for send_email)"},
                "body": {"type": "string", "description": "Email body (for send_email)"},
                "to_email": {"type": "string", "description": "Recipient email (for send_email)"},
                "message_id": {"type": "string", "description": "Message ID (for get_message)"},
                "max_results": {"type": "integer", "description": "Max results to return (for list_messages)"},
            },
            "required": ["action"],
        }

    async def execute(self, action: str = "", **kwargs) -> ToolResult:
        """Execute Gmail API action with OAuth2 authentication"""
        service = self._get_service()
        if not service:
            return ToolResult(
                success=False, output="", error="Gmail API credentials not available. Run OAuth2 flow first."
            )

        try:
            if action == "send_email":
                return await self._send_email(**kwargs)
            if action == "list_messages":
                return await self._list_messages(**kwargs)
            if action == "get_message":
                return await self._get_message(**kwargs)
            return ToolResult(success=False, output="", error=f"Unknown action: {action}")
        except HttpError as error:
            return ToolResult(success=False, output="", error=f"Gmail API error: {error}")
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error executing Gmail API action: {e}")

    async def _send_email(self, subject: str = "", body: str = "", to_email: str = "", **kwargs) -> ToolResult:
        """Send email using Gmail API"""
        if not subject or not body or not to_email:
            return ToolResult(
                success=False, output="", error="Missing required parameters for send_email: subject, body, to_email"
            )

        service = self._get_service()
        if not service:
            return ToolResult(success=False, output="", error="Gmail API service not available")

        # Create message
        message = {
            "raw": base64.urlsafe_b64encode(
                f"From: {settings.gmail_address}\r\n"
                f"To: {to_email}\r\n"
                f"Subject: {subject}\r\n"
                f"Content-Type: text/plain; charset=UTF-8\r\n"
                f"Content-Transfer-Encoding: 7bit\r\n\r\n"
                f"{body}".encode()
            ).decode()
        }

        try:
            sent_message = service.users().messages().send(userId="me", body=message).execute()
            return ToolResult(success=True, output=f"Email sent: {sent_message['id']}", error=None)
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Failed to send email: {e}")

    async def _list_messages(self, max_results: int = 10, **kwargs) -> ToolResult:
        """List messages from Gmail inbox"""
        service = self._get_service()
        if not service:
            return ToolResult(success=False, output="", error="Gmail API service not available")

        try:
            results = service.users().messages().list(userId="me", maxResults=max_results).execute()
            messages = results.get("messages", [])
            message_ids = [msg["id"] for msg in messages]
            return ToolResult(success=True, output=f"Found {len(messages)} messages: {message_ids}", error=None)
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Failed to list messages: {e}")

    async def _get_message(self, message_id: str = "", **kwargs) -> ToolResult:
        """Get message details from Gmail"""
        if not message_id:
            return ToolResult(success=False, output="", error="Missing message_id parameter")

        service = self._get_service()
        if not service:
            return ToolResult(success=False, output="", error="Gmail API service not available")

        try:
            message = service.users().messages().get(userId="me", id=message_id).execute()
            return ToolResult(success=True, output=f"Message {message_id} details: {message['snippet']}", error=None)
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Failed to get message: {e}")
