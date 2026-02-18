import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from jarvis.config import settings
from jarvis.tools.base import Tool, ToolResult
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import base64
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import os
import pickle

# OAuth2 scopes for Gmail API
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

# Path to the token file
TOKEN_PATH = os.path.join(os.path.dirname(__file__), 'gmail_token.pickle')

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

    async def execute(self, subject: str = "", body: str = "", to_email: str = "", to: str = "", **kwargs) -> ToolResult:
        # Accept both "to" and "to_email" (LLMs use different names)
        recipient = to_email or to or kwargs.get("recipient", "")
        if not recipient:
            return ToolResult(success=False, output="",
                              error="Missing recipient — provide 'to_email' or 'to' parameter")
        if not subject:
            return ToolResult(success=False, output="", error="Missing 'subject' parameter")
        if not body:
            return ToolResult(success=False, output="", error="Missing 'body' parameter")

        # Authenticate using OAuth2
        creds = None
        # Load existing token if available
        if os.path.exists(TOKEN_PATH):
            with open(TOKEN_PATH, 'rb') as token:
                creds = pickle.load(token)
        # If there are no valid credentials, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                credentials_path = os.path.join(settings.data_dir, 'gmail_credentials.json')
                flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)

        # Save the credentials for the next run
        with open(TOKEN_PATH, 'wb') as token:
            pickle.dump(creds, token)

        # Use the credentials to send the email
        service = build('gmail', 'v1', credentials=creds)
        message = MIMEText(body)
        message['to'] = recipient
        message['subject'] = subject
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

        try:
            message = (service.users().messages().send(userId='me', body={
                'raw': raw_message
            }).execute())
            return ToolResult(success=True, output=f"Email sent to {recipient}", error=None)
        except HttpError as error:
            return ToolResult(success=False, output="", error=f"Failed to send email: {error}")