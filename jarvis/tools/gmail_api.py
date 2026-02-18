import os
import base64
import json
import datetime
from typing import Optional, List, Dict, Any

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from jarvis.config import settings
from jarvis.tools.base import Tool, ToolResult


class GmailAPITool(Tool):
    name = "gmail_api"
    description = "Interacts with Gmail API using OAuth2 authentication"
    timeout_seconds = 30

    # Scopes required for Gmail API
    SCOPES = ['https://www.googleapis.com/auth/gmail.send',
              'https://www.googleapis.com/auth/gmail.readonly']

    def __init__(self):
        super().__init__()
        self._credentials = None
        self._service = None
        self._load_credentials()

    def _load_credentials(self):
        """Load or create OAuth2 credentials"""
        creds = None
        token_path = settings.data_dir + '/gmail_token.json'
        credentials_path = settings.data_dir + '/gmail_credentials.json'

        # Check if token exists
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, self.SCOPES)

        # Check if credentials exist and token doesn't (need refresh)
        if not creds and os.path.exists(credentials_path):
            creds = self._refresh_credentials(credentials_path, token_path)

        # If no credentials, we need to run OAuth flow (manual process)
        if not creds:
            self._credentials = None
            self._service = None
            return

        # Check if token is expired and refresh if needed
        if creds and creds.expired:
            creds.refresh(Request())
            with open(token_path, 'w') as token:
                token.write(creds.to_json())

        self._credentials = creds
        self._service = build('gmail', 'v1', credentials=creds)

    def _refresh_credentials(self, credentials_path: str, token_path: str) -> Optional[Credentials]:
        """Refresh credentials from credentials file"""
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_path, self.SCOPES)
            creds = flow.run_local_server(port=0)
            with open(token_path, 'w') as token:
                token.write(creds.to_json())
            return creds
        except Exception as e:
            print(f"Error refreshing credentials: {e}")
            return None

    def _get_service(self) -> Optional[Any]:
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
                    "enum": ["send_email", "list_messages", "get_message"]
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject (for send_email)"
                },
                "body": {
                    "type": "string",
                    "description": "Email body (for send_email)"
                },
                "to_email": {
                    "type": "string",
                    "description": "Recipient email (for send_email)"
                },
                "message_id": {
                    "type": "string",
                    "description": "Message ID (for get_message)"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max results to return (for list_messages)"
                }
            },
            "required": ["action"]
        }

    async def execute(self, action: str = "", **kwargs) -> ToolResult:
        """Execute Gmail API action with OAuth2 authentication"""
        service = self._get_service()
        if not service:
            return ToolResult(
                success=False,
                output="",
                error="Gmail API credentials not available. Run OAuth2 flow first."
            )

        try:
            if action == "send_email":
                return await self._send_email(**kwargs)
            elif action == "list_messages":
                return await self._list_messages(**kwargs)
            elif action == "get_message":
                return await self._get_message(**kwargs)
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unknown action: {action}"
                )
        except HttpError as error:
            return ToolResult(
                success=False,
                output="",
                error=f"Gmail API error: {error}"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Error executing Gmail API action: {e}"
            )

    async def _send_email(self, subject: str = "", body: str = "", to_email: str = "", **kwargs) -> ToolResult:
        """Send email using Gmail API"""
        if not subject or not body or not to_email:
            return ToolResult(
                success=False,
                output="",
                error="Missing required parameters for send_email: subject, body, to_email"
            )

        service = self._get_service()
        if not service:
            return ToolResult(
                success=False,
                output="",
                error="Gmail API service not available"
            )

        # Create message
        message = {
            'raw': base64.urlsafe_b64encode(
                f"From: {settings.gmail_address}\r\n"
                f"To: {to_email}\r\n"
                f"Subject: {subject}\r\n"
                f"Content-Type: text/plain; charset=UTF-8\r\n"
                f"Content-Transfer-Encoding: 7bit\r\n\r\n"
                f"{body}".encode()
            ).decode()
        }

        try:
            sent_message = service.users().messages().send(
                userId='me', body=message).execute()
            return ToolResult(
                success=True,
                output=f"Email sent: {sent_message['id']}",
                error=None
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to send email: {e}"
            )

    async def _list_messages(self, max_results: int = 10, **kwargs) -> ToolResult:
        """List messages from Gmail inbox"""
        service = self._get_service()
        if not service:
            return ToolResult(
                success=False,
                output="",
                error="Gmail API service not available"
            )

        try:
            results = service.users().messages().list(
                userId='me', maxResults=max_results).execute()
            messages = results.get('messages', [])
            message_ids = [msg['id'] for msg in messages]
            return ToolResult(
                success=True,
                output=f"Found {len(messages)} messages: {message_ids}",
                error=None
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to list messages: {e}"
            )

    async def _get_message(self, message_id: str = "", **kwargs) -> ToolResult:
        """Get message details from Gmail"""
        if not message_id:
            return ToolResult(
                success=False,
                output="",
                error="Missing message_id parameter"
            )

        service = self._get_service()
        if not service:
            return ToolResult(
                success=False,
                output="",
                error="Gmail API service not available"
            )

        try:
            message = service.users().messages().get(
                userId='me', id=message_id).execute()
            return ToolResult(
                success=True,
                output=f"Message {message_id} details: {message['snippet']}",
                error=None
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to get message: {e}"
            )