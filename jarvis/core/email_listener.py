import asyncio
import email
import imaplib
import socket
from collections.abc import Callable
from dataclasses import dataclass
from email.header import decode_header

from jarvis.config import settings
from jarvis.observability.logger import get_logger

log = get_logger("email_listener")


CREATOR_EMAIL = "ristlin@gmail.com"
GMAIL_IMAP_HOST = "imap.gmail.com"
GMAIL_IMAP_PORT = 993


@dataclass
class EmailMessage:
    uid: str
    from_addr: str
    subject: str
    date: str
    body_text: str


def _decode_mime_header(value: str | None) -> str:
    if not value:
        return ""
    try:
        parts = decode_header(value)
        out = []
        for text, enc in parts:
            if isinstance(text, bytes):
                out.append(text.decode(enc or "utf-8", errors="replace"))
            else:
                out.append(str(text))
        return "".join(out)
    except Exception:
        return str(value)


def _extract_text_from_message(msg: email.message.Message) -> str:
    # Prefer text/plain; fallback to first text/* part.
    try:
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                disp = (part.get("Content-Disposition") or "").lower()
                if ctype == "text/plain" and "attachment" not in disp:
                    payload = part.get_payload(decode=True) or b""
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype.startswith("text/"):
                    payload = part.get_payload(decode=True) or b""
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
            return ""
        payload = msg.get_payload(decode=True) or b""
        charset = msg.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")
    except Exception:
        return ""


class EmailInboxListener:
    """Polls Gmail IMAP for new messages and enqueues them into the core loop.

    Disabled by default. Requires settings.gmail_address and settings.gmail_password.

    Notes:
      - For Gmail, this typically requires an App Password (2FA enabled).
      - Uses IMAP UID search for UNSEEN messages.
    """

    def __init__(
        self,
        enqueue_fn: Callable[[str], object],
        interval_seconds: int | None = None,
    ):
        self._enqueue_fn = enqueue_fn
        self._interval = float(interval_seconds or settings.email_listener_interval_seconds)
        self._running = False
        self._task: asyncio.Task | None = None
        self._disabled_reason: str | None = None

    def start(self):
        if self._task is not None:
            return
        self._running = True
        self._task = asyncio.create_task(self._run(), name="email_inbox_listener")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def _check_enabled_and_creds(self) -> bool:
        if not getattr(settings, "email_listener_enabled", False):
            self._disabled_reason = "disabled_by_config"
            return False

        if not settings.gmail_address or not settings.gmail_app_password:
            self._disabled_reason = "missing_gmail_credentials"
            log.error(
                "email_listener_disabled_missing_credentials",
                gmail_address=bool(settings.gmail_address),
                gmail_app_password=bool(settings.gmail_app_password),
            )
            return False

        return True

    def _imap_connect(self) -> imaplib.IMAP4_SSL:
        # imaplib is blocking; we run it in a thread via asyncio.to_thread.
        client = imaplib.IMAP4_SSL(GMAIL_IMAP_HOST, GMAIL_IMAP_PORT)
        client.login(settings.gmail_address, settings.gmail_app_password)
        client.select("INBOX")
        return client

    def _fetch_unseen(self) -> list[EmailMessage]:
        client: imaplib.IMAP4_SSL | None = None
        try:
            client = self._imap_connect()
            typ, data = client.uid("search", None, "UNSEEN")
            if typ != "OK":
                raise RuntimeError(f"IMAP search failed: {typ} {data}")

            uids = (data[0] or b"").split()
            messages: list[EmailMessage] = []
            for uid_b in uids:
                uid = uid_b.decode("utf-8", errors="replace")
                typ, msg_data = client.uid("fetch", uid, "(RFC822)")
                if typ != "OK" or not msg_data or not msg_data[0]:
                    continue

                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)
                from_addr = _decode_mime_header(msg.get("From"))
                subject = _decode_mime_header(msg.get("Subject"))
                date = _decode_mime_header(msg.get("Date"))
                body_text = _extract_text_from_message(msg)

                messages.append(
                    EmailMessage(
                        uid=uid,
                        from_addr=from_addr,
                        subject=subject,
                        date=date,
                        body_text=body_text,
                    )
                )

            # Prioritize creator emails first
            def _prio(m: EmailMessage) -> int:
                return 0 if CREATOR_EMAIL.lower() in (m.from_addr or "").lower() else 1

            messages.sort(key=_prio)
            return messages
        finally:
            if client is not None:
                try:
                    client.logout()
                except Exception:
                    pass

    async def _run(self):
        if not self._check_enabled_and_creds():
            log.info("email_listener_not_running", reason=self._disabled_reason)
            return

        log.info(
            "email_listener_started",
            interval_seconds=self._interval,
            gmail_address=settings.gmail_address,
        )

        # Basic backoff on errors
        backoff = 1.0
        while self._running:
            try:
                messages = await asyncio.to_thread(self._fetch_unseen)
                if messages:
                    log.info("email_listener_new_messages", count=len(messages))
                for m in messages:
                    # Only enqueue creator emails for now (explicit requirement).
                    if CREATOR_EMAIL.lower() not in (m.from_addr or "").lower():
                        log.info(
                            "email_listener_skipping_non_creator",
                            uid=m.uid,
                            from_addr=m.from_addr,
                            subject=m.subject,
                        )
                        continue

                    payload = (
                        "New email received\n"
                        f"From: {m.from_addr}\n"
                        f"Date: {m.date}\n"
                        f"Subject: {m.subject}\n\n"
                        f"Body:\n{m.body_text.strip()}\n"
                    )
                    self._enqueue_fn(payload)
                    log.info(
                        "email_listener_enqueued",
                        uid=m.uid,
                        from_addr=m.from_addr,
                        subject=m.subject,
                    )

                backoff = 1.0
                await asyncio.sleep(self._interval)
            except (imaplib.IMAP4.error, socket.gaierror, ConnectionError, TimeoutError) as e:
                log.error("email_listener_connection_error", error=str(e))
                await asyncio.sleep(min(self._interval, 5 * backoff))
                backoff = min(backoff * 2.0, 300.0)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.error("email_listener_unhandled_error", error=str(e))
                await asyncio.sleep(min(self._interval, 5 * backoff))
                backoff = min(backoff * 2.0, 300.0)
