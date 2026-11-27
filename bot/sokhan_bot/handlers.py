"""aiogram message and callback handlers for the Sokhan bot."""

import io
import logging
import time
from collections.abc import Callable
from typing import TypeVar

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    User,
)

from sokhan_bot import texts
from sokhan_bot.client import (
    AuthError,
    BackendError,
    FileTooLongError,
    QuotaError,
    SokhanClient,
)
from sokhan_bot.split import split_message
from sokhan_bot.store import TokenStore

logger = logging.getLogger(__name__)

_RATE_LIMIT_SECONDS = 10.0

T = TypeVar("T")


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
        self.router.message.register(self.upgrade, Command("upgrade"))
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

    def _authed(self, chat_id: int, user: User, call: Callable[[str], T]) -> T:
        """Run `call(token)`, re-registering once if the API revoked the token.

        A web logout or a newer sign-in revokes the token cached for this
        chat; without the retry every later request would fail. Raises
        BackendError when the backend is unreachable or rejects again.
        """
        token = self.store.get(chat_id)
        if token:
            try:
                return call(token)
            except AuthError:
                logger.info("token for chat %s was revoked; re-registering", chat_id)
                self.store.forget(chat_id)
        token = self.client.register_telegram(user.id, user.username)
        self.store.set(chat_id, token)
        return call(token)

    async def start(self, message: Message) -> None:
        token = await self._ensure_token(message)
        if not token:
            return
        # The cached token doubles as the connect code, so make sure it still
        # works before showing it; a backend outage keeps the cached one.
        try:
            self._authed(message.chat.id, message.from_user, self.client.get_quota)
        except BackendError:
            pass
        token = self.store.get(message.chat.id) or token
        await message.answer(texts.WELCOME.format(connect_code=token))

    async def quota(self, message: Message) -> None:
        token = await self._ensure_token(message)
        if not token:
            return
        try:
            info = self._authed(message.chat.id, message.from_user, self.client.get_quota)
        except BackendError:
            await message.answer(texts.SERVER_UNREACHABLE)
            return
        await message.answer(
            texts.QUOTA_LINE.format(
                plan=texts.PLAN_LABELS.get(info.get("plan", "free"), info.get("plan", "free")),
                used=round(info["used_minutes"], 1),
                limit=info["limit_minutes"],
                remaining=round(info["remaining_minutes"], 1),
                max_file=info.get("max_file_minutes", 10),
            )
        )

    async def upgrade(self, message: Message) -> None:
        """Render the plan catalogue so users know what a subscription buys."""
        try:
            plans = self.client.get_plans()
        except BackendError:
            await message.answer(texts.SERVER_UNREACHABLE)
            return
        lines = [texts.UPGRADE_HEADER]
        for plan in plans:
            lines.append(
                texts.UPGRADE_PLAN_LINE.format(
                    title=texts.PLAN_LABELS.get(plan["code"], plan["code"]),
                    max_file=plan["max_file_minutes"],
                    monthly=plan["monthly_minutes"],
                )
            )
        lines.append("")
        lines.append(texts.UPGRADE_FOOTER)
        await message.answer("\n".join(lines))

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
            job = self._authed(
                message.chat.id, message.from_user, lambda t: self.client.get_job(t, job_id)
            )
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

        # Pre-flight guard: Telegram reports the duration up front, so a
        # file longer than the plan's per-file cap is refused before any
        # download. If the quota lookup fails, fall through — the backend
        # enforces its own caps on upload anyway.
        duration = getattr(media, "duration", None)
        if duration:
            try:
                max_file = int(self.client.get_quota(token).get("max_file_minutes", 10))
                if max_file and duration > max_file * 60:
                    await message.answer(
                        texts.FILE_TOO_LONG.format(
                            file_minutes=round(duration / 60.0, 1), max_file=max_file
                        )
                    )
                    return
            except BackendError:
                pass

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
            job_id = self._authed(
                message.chat.id,
                message.from_user,
                lambda t: self.client.upload_audio(t, filename, content),
            )
        except FileTooLongError as exc:
            await message.answer(
                texts.FILE_TOO_LONG.format(
                    file_minutes=round(exc.file_minutes, 1), max_file=exc.max_file_minutes
                )
            )
            return
        except QuotaError:
            await message.answer(texts.QUOTA_EXHAUSTED)
            return
        except BackendError as exc:
            await message.answer(texts.JOB_FAILED.format(error=exc))
            return

        await message.answer(texts.VOICE_RECEIVED)
        self.store.track(job_id, message.chat.id)
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
            job = self._authed(
                callback.message.chat.id,
                callback.from_user,
                lambda t: self.client.get_job(t, job_id),
            )
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
