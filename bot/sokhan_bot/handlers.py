"""aiogram message and callback handlers for the Sokhan bot."""

import io
import logging
import time

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from sokhan_bot import texts
from sokhan_bot.client import BackendError, QuotaError, SokhanClient
from sokhan_bot.split import split_message
from sokhan_bot.store import TokenStore

logger = logging.getLogger(__name__)

_RATE_LIMIT_SECONDS = 10.0


def _job_keyboard(job_id: str, web_base_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.SUMMARY_BUTTON, callback_data=f"summary:{job_id}"
                ),
                InlineKeyboardButton(
                    text=texts.WEB_ARCHIVE_BUTTON,
                    url=f"{web_base_url}/fa/jobs/{job_id}",
                ),
            ]
        ]
    )


class Handlers:
    """Handler group sharing one backend client and token store."""

    def __init__(self, client: SokhanClient, store: TokenStore) -> None:
        self.client = client
        self.store = store
        self._last_job_at: dict[int, float] = {}

        self.router = Router(name="sokhan")
        self.router.message.register(self.start, CommandStart())
        self.router.message.register(self.quota, Command("quota"))
        self.router.message.register(self.track, Command("track"))
        self.router.message.register(
            self.media,
            F.voice | F.audio | F.video | F.video_note | F.document,
        )
        self.router.callback_query.register(
            self.summary, F.data.startswith("summary:")
        )

    def _rate_limited(self, chat_id: int) -> bool:
        now = time.monotonic()
        if now - self._last_job_at.get(chat_id, 0.0) < _RATE_LIMIT_SECONDS:
            return True
        self._last_job_at[chat_id] = now
        return False

    async def _ensure_token(self, message: Message) -> str | None:
        token = self.store.get(message.chat.id)
        if token:
            return token
        try:
            token = self.client.register_telegram(
                message.from_user.id, message.from_user.username
            )
        except BackendError:
            logger.exception("telegram register failed")
            await message.answer(texts.SERVER_UNREACHABLE)
            return None
        self.store.set(message.chat.id, token)
        return token

    async def start(self, message: Message) -> None:
        token = await self._ensure_token(message)
        if not token:
            return
        await message.answer(texts.WELCOME.format(connect_code=token))

    async def quota(self, message: Message) -> None:
        token = await self._ensure_token(message)
        if not token:
            return
        try:
            info = self.client.get_quota(token)
        except BackendError:
            await message.answer(texts.SERVER_UNREACHABLE)
            return
        await message.answer(
            texts.QUOTA_LINE.format(
                used=round(info["used_minutes"], 1),
                limit=info["limit_minutes"],
                remaining=round(info["remaining_minutes"], 1),
            )
        )

    async def track(self, message: Message, command: CommandObject) -> None:
        token = self.store.get(message.chat.id)
        if not token:
            await message.answer(texts.NEED_START)
            return
        job_id = (command.args or "").strip()
        if not job_id:
            await message.answer("شناسهٔ پردازش را بنویس، مثلاً: /track 3f2a…")
            return
        try:
            job = self.client.get_job(token, job_id)
        except BackendError:
            await message.answer(texts.UNKNOWN_JOB)
            return
        await message.answer(
            texts.STATUS_LINE.format(
                status=texts.STATUS_LABELS.get(job["status"], job["status"]),
                progress=round(job["progress"]),
            )
        )

    async def media(self, message: Message, bot: Bot) -> None:
        if self._rate_limited(message.chat.id):
            await message.answer(texts.RATE_LIMITED)
            return
        token = await self._ensure_token(message)
        if not token:
            return

        media = (
            message.voice
            or message.audio
            or message.video
            or message.video_note
            or message.document
        )
        if media is None:
            return
        filename = getattr(media, "file_name", None) or f"voice-{media.file_unique_id}.ogg"

        try:
            telegram_file = await bot.get_file(media.file_id)
            buffer = io.BytesIO()
            await bot.download_file(telegram_file.file_path, destination=buffer)
            content = buffer.getvalue()
        except Exception:
            logger.exception("failed to download media")
            await message.answer(texts.DOWNLOAD_FAILED)
            return

        try:
            job_id = self.client.upload_audio(token, filename, content)
        except QuotaError:
            await message.answer(texts.QUOTA_EXHAUSTED)
            return
        except BackendError as exc:
            await message.answer(texts.JOB_FAILED.format(error=exc))
            return

        await message.answer(texts.VOICE_RECEIVED)
        await message.answer(
            f"شناسهٔ پردازش: {job_id}\nبا /track {job_id} وضعیت را دنبال کن.",
            reply_markup=_job_keyboard(job_id, self.client.settings.web_base_url),
        )

    async def summary(self, callback: CallbackQuery) -> None:
        if callback.message is None or callback.data is None:
            await callback.answer()
            return
        token = self.store.get(callback.message.chat.id)
        if not token:
            await callback.answer(texts.NEED_START, show_alert=True)
            return

        job_id = callback.data.split(":", 1)[1]
        try:
            job = self.client.get_job(token, job_id)
        except BackendError:
            await callback.answer(texts.UNKNOWN_JOB, show_alert=True)
            return

        if job.get("summary"):
            for chunk in split_message(job["summary"]):
                await callback.message.answer(chunk)
            await callback.answer()
        elif job.get("want_summary"):
            await callback.answer(texts.SUMMARY_NOT_READY, show_alert=True)
        else:
            await callback.answer(texts.SUMMARY_DISABLED, show_alert=True)
