import asyncio
import os
import tempfile
from collections.abc import Callable

import aiohttp

from jarvis.config import settings
from jarvis.observability.logger import get_logger

log = get_logger("telegram_listener")


class TelegramListener:
    """Polls Telegram Bot API for incoming messages and enqueues them into the core loop.

    Uses long-polling via getUpdates (no public URL/webhook needed).
    Only processes messages from the configured TELEGRAM_CHAT_ID (creator only).
    """

    def __init__(
        self,
        enqueue_fn: Callable[[str], object],
        reply_fn: Callable[[str], object] | None = None,
        interval_seconds: int | None = None,
    ):
        self._enqueue_fn = enqueue_fn
        self._reply_fn = reply_fn
        self._interval = float(interval_seconds or settings.telegram_polling_interval)
        self._running = False
        self._task: asyncio.Task | None = None
        self._disabled_reason: str | None = None
        self._last_update_id: int = 0

    @property
    def base_url(self) -> str:
        return f"https://api.telegram.org/bot{settings.telegram_bot_token}"

    def start(self):
        if self._task is not None:
            return
        self._running = True
        self._task = asyncio.create_task(self._run(), name="telegram_listener")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def _check_enabled(self) -> bool:
        if not getattr(settings, "telegram_listener_enabled", False):
            self._disabled_reason = "disabled_by_config"
            return False
        if not settings.telegram_bot_token:
            self._disabled_reason = "missing_bot_token"
            log.error("telegram_listener_disabled", reason="TELEGRAM_BOT_TOKEN not set")
            return False
        if not settings.telegram_chat_id:
            self._disabled_reason = "missing_chat_id"
            log.error("telegram_listener_disabled", reason="TELEGRAM_CHAT_ID not set")
            return False
        return True

    async def _fetch_updates(self, session: aiohttp.ClientSession) -> list[dict]:
        params = {"timeout": 30, "allowed_updates": '["message"]'}
        if self._last_update_id:
            params["offset"] = self._last_update_id + 1

        async with session.get(
            f"{self.base_url}/getUpdates", params=params, timeout=aiohttp.ClientTimeout(total=40)
        ) as resp:
            data = await resp.json()
            if not data.get("ok"):
                raise RuntimeError(f"Telegram API error: {data.get('description', 'unknown')}")
            return data.get("result", [])

    def _extract_message_text(self, update: dict) -> str | None:
        """Extract text content from a Telegram update. Returns None if not from creator."""
        msg = update.get("message")
        if not msg:
            return None

        chat_id = str(msg.get("chat", {}).get("id", ""))
        if chat_id != str(settings.telegram_chat_id):
            log.info("telegram_ignoring_non_creator", chat_id=chat_id)
            return None

        text = msg.get("text")
        if text:
            return text

        caption = msg.get("caption")
        if caption:
            return caption

        return None

    async def _extract_voice_text(self, update: dict, session: aiohttp.ClientSession) -> str | None:
        """Extract and transcribe voice/audio messages. Returns transcribed text or None."""
        msg = update.get("message")
        if not msg:
            return None

        chat_id = str(msg.get("chat", {}).get("id", ""))
        if chat_id != str(settings.telegram_chat_id):
            return None

        voice = msg.get("voice") or msg.get("audio")
        if not voice:
            return None

        file_id = voice.get("file_id")
        if not file_id:
            return None

        try:
            async with session.get(f"{self.base_url}/getFile", params={"file_id": file_id}) as resp:
                data = await resp.json()
                if not data.get("ok"):
                    log.warning("telegram_get_file_failed", error=data.get("description"))
                    return None
                file_path = data["result"]["file_path"]

            file_url = f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{file_path}"
            async with session.get(file_url) as resp:
                audio_bytes = await resp.read()

            transcription = await self._transcribe_audio(audio_bytes, file_path)
            if transcription:
                log.info("telegram_voice_transcribed", length=len(transcription))
                return transcription
        except Exception as e:
            log.error("telegram_voice_error", error=str(e))
        return None

    async def _transcribe_audio(self, audio_bytes: bytes, filename: str) -> str | None:
        """Transcribe audio using OpenAI Whisper API."""
        if not settings.openai_api_key:
            log.warning("whisper_unavailable", reason="OPENAI_API_KEY not set")
            return None

        try:
            suffix = os.path.splitext(filename)[1] or ".ogg"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            try:
                import openai

                client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
                with open(tmp_path, "rb") as audio_file:
                    transcript = await client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                    )
                return transcript.text
            finally:
                os.unlink(tmp_path)
        except Exception as e:
            log.error("whisper_transcription_failed", error=str(e))
            return None

    async def _run(self):
        if not self._check_enabled():
            log.info("telegram_listener_not_running", reason=self._disabled_reason)
            return

        log.info(
            "telegram_listener_started",
            interval_seconds=self._interval,
            chat_id=settings.telegram_chat_id,
        )

        backoff = 1.0
        async with aiohttp.ClientSession() as session:
            while self._running:
                try:
                    updates = await self._fetch_updates(session)

                    for update in updates:
                        update_id = update.get("update_id", 0)
                        self._last_update_id = max(self._last_update_id, update_id)

                        text = self._extract_message_text(update)
                        if not text:
                            text = await self._extract_voice_text(update, session)
                            if text:
                                text = f"[voice] {text}"

                        if text:
                            payload = f"[Telegram] {text}"
                            self._enqueue_fn(payload)
                            log.info("telegram_message_enqueued", length=len(text), preview=text[:100])

                    backoff = 1.0
                    if not updates:
                        await asyncio.sleep(self._interval)

                except asyncio.CancelledError:
                    raise
                except (aiohttp.ClientError, TimeoutError, ConnectionError) as e:
                    log.error("telegram_listener_connection_error", error=str(e))
                    await asyncio.sleep(min(self._interval, 5 * backoff))
                    backoff = min(backoff * 2.0, 300.0)
                except Exception as e:
                    log.error("telegram_listener_unhandled_error", error=str(e))
                    await asyncio.sleep(min(self._interval, 5 * backoff))
                    backoff = min(backoff * 2.0, 300.0)

    async def send_reply(self, text: str, voice: bool = False) -> bool:
        """Send a reply back to the creator's Telegram chat (text or voice)."""
        if not settings.telegram_bot_token or not settings.telegram_chat_id:
            return False
        try:
            async with aiohttp.ClientSession() as session:
                if voice and settings.openai_api_key:
                    return await self._send_voice_reply(session, text)

                payload = {
                    "chat_id": settings.telegram_chat_id,
                    "text": text[:4096],
                    "parse_mode": "Markdown",
                }
                async with session.post(
                    f"{self.base_url}/sendMessage", json=payload, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    data = await resp.json()
                    if data.get("ok"):
                        log.info("telegram_reply_sent", length=len(text))
                        return True
                    # Retry without parse_mode if Markdown fails
                    payload.pop("parse_mode", None)
                    async with session.post(
                        f"{self.base_url}/sendMessage", json=payload, timeout=aiohttp.ClientTimeout(total=10)
                    ) as retry_resp:
                        retry_data = await retry_resp.json()
                        if retry_data.get("ok"):
                            return True
                    log.warning("telegram_reply_failed", error=data.get("description"))
                    return False
        except Exception as e:
            log.error("telegram_reply_error", error=str(e))
            return False

    async def _send_voice_reply(self, session: aiohttp.ClientSession, text: str) -> bool:
        """Generate TTS audio and send as voice message."""
        try:
            import openai

            client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

            tts_text = text[:4096]
            response = await client.audio.speech.create(
                model="tts-1",
                voice="onyx",
                input=tts_text,
                response_format="opus",
            )

            audio_bytes = response.content

            data = aiohttp.FormData()
            data.add_field("chat_id", str(settings.telegram_chat_id))
            data.add_field("voice", audio_bytes, filename="reply.ogg", content_type="audio/ogg")

            async with session.post(
                f"{self.base_url}/sendVoice", data=data, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                result = await resp.json()
                if result.get("ok"):
                    log.info("telegram_voice_reply_sent", text_length=len(text))
                    return True
                log.warning("telegram_voice_reply_failed", error=result.get("description"))

            # Fallback to text if voice fails
            return False
        except Exception as e:
            log.error("telegram_tts_error", error=str(e))
            return False
