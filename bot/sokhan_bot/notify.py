"""Push notifications and live progress for tracked jobs.

When the bot receives a voice message it shows a progress message and says
the transcript will follow — this worker keeps both promises. Every few
seconds it polls the jobs the store is tracking: while a job runs, the
progress message is edited in place with a live bar (only when something
actually moved, so Telegram is not spammed); the moment a job completes,
the progress message is deleted and the transcript is pushed (split into
Telegram-sized chunks); a failed job gets an apology instead. The backend
always keeps working even if the bot process dies and comes back, because
the watch list is persisted in the token store.

The decision logic lives in module-level functions so tests need neither
aiogram nor a network.
"""

import asyncio
import logging
import time

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from sokhan_bot import texts
from sokhan_bot.client import AuthError, SokhanClient
from sokhan_bot.split import split_message
from sokhan_bot.store import TokenStore

logger = logging.getLogger(__name__)

# After this long a job is presumed stuck; we stop watching it.
GIVE_UP_SECONDS = 6 * 3600

# Cells in the live progress bar; a Telegram line stays comfortably narrow.
BAR_CELLS = 10


def progress_bar(percent: float, cells: int = BAR_CELLS) -> str:
    """A textual bar: filled ▓ cells for the completed share, ░ for the rest."""
    capped = max(0.0, min(100.0, percent))
    filled = min(cells, int(capped * cells / 100 + 0.5))
    return "▓" * filled + "░" * (cells - filled)


def progress_message(job: dict) -> str:
    """The live-progress text for a queued or processing job.

    Shared by the upload handler (initial message) and the notifier (edits),
    so what the user first sees is exactly what later edits render.
    """
    percent = max(0.0, min(100.0, float(job.get("progress") or 0.0)))
    status = str(job.get("status") or "queued")
    label = texts.STATUS_LABELS.get(status, status)
    return "\n".join(
        [
            f"شناسهٔ پردازش: {job.get('id', '—')}",
            texts.PROGRESS_LINE.format(
                bar=progress_bar(percent),
                percent=texts.fa_digits(int(percent + 0.5)),
                status=label,
            ),
        ]
    )


def completion_message(job: dict) -> str | None:
    """The message to send for a finished job, or None while it still runs."""
    status = job.get("status")
    if status == "completed":
        transcript = (job.get("text") or "").strip()
        if transcript:
            return texts.TRANSCRIPT_READY.format(transcript=transcript)
        return texts.TRANSCRIPT_EMPTY
    if status == "failed":
        error = job.get("error") or "—"
        return texts.NOTIFY_FAILED.format(error=error)
    return None


class CompletionNotifier:
    """Background loop delivering transcripts for tracked jobs."""

    def __init__(
        self,
        bot: Bot,
        client: SokhanClient,
        store: TokenStore,
        poll_interval_seconds: float = 5.0,
    ) -> None:
        self.bot = bot
        self.client = client
        self.store = store
        self.poll_interval_seconds = poll_interval_seconds

    async def poll_once(self) -> None:
        """One sweep over the tracked jobs; safe to call from tests."""
        for job_id, chat_id, since in self.store.tracked():
            if time.time() - since > GIVE_UP_SECONDS:
                logger.warning("job %s waited over %d s; giving up", job_id, GIVE_UP_SECONDS)
                await self._forget_progress_message(job_id, chat_id)
                await self._send(chat_id, texts.NOTIFY_TIMEOUT.format(job_id=job_id))
                self.store.untrack(job_id)
                continue

            token = self.store.get(chat_id)
            if not token:
                logger.warning("no token for chat %s; untracking job %s", chat_id, job_id)
                self.store.untrack(job_id)
                continue

            try:
                job = await asyncio.to_thread(self.client.get_job, token, job_id)
            except AuthError:
                # Revoked by a web logout or a newer sign-in. The poller has
                # no Telegram user to re-register with, so it asks for /start.
                logger.warning("token for chat %s was revoked; untracking job %s", chat_id, job_id)
                self.store.forget(chat_id)
                self.store.untrack(job_id)
                await self._send(chat_id, texts.NEED_START)
                continue
            except Exception:
                logger.exception("job fetch failed (%s); will retry", job_id)
                continue

            message = completion_message(job)
            if message is None:
                await self._report_progress(job_id, chat_id, job)
                continue

            await self._forget_progress_message(job_id, chat_id)
            delivered = await self._send_all(chat_id, message)
            if delivered:
                self.store.untrack(job_id)

    async def _report_progress(self, job_id: str, chat_id: int, job: dict) -> None:
        """Edit the tracked message with a live bar when something moved.

        The rendered text only changes when the percent or the status does,
        so a queued job sitting at 0% costs one edit per real change — not
        one per sweep. Watches recorded without a message id (older bot
        versions) skip live progress entirely.
        """
        watch = self.store.watch(job_id)
        message_id = watch.get("message_id") if watch else None
        if not message_id:
            return

        percent = max(0.0, min(100.0, float(job.get("progress") or 0.0)))
        status = str(job.get("status") or "queued")
        if watch.get("progress") == percent and watch.get("status") == status:
            return

        self.store.set_progress(job_id, percent, status)
        try:
            await self.bot.edit_message_text(
                progress_message(job), chat_id=chat_id, message_id=message_id
            )
        except TelegramBadRequest:
            # "message to edit not found" and friends: the user deleted the
            # message (or it is gone). Stop editing; completion still arrives.
            logger.info("progress message for job %s is gone; live edits stopped", job_id)
            self.store.drop_message_id(job_id)
        except Exception:
            logger.exception("progress edit failed for job %s; will retry", job_id)
            self.store.set_progress(
                job_id,
                float(watch.get("progress") or 0.0),
                str(watch.get("status") or "queued"),
            )

    async def _forget_progress_message(self, job_id: str, chat_id: int) -> None:
        """Delete the progress message once a job left the running state."""
        watch = self.store.watch(job_id)
        message_id = watch.get("message_id") if watch else None
        if not message_id:
            return
        self.store.drop_message_id(job_id)
        try:
            await self.bot.delete_message(chat_id, message_id)
        except Exception:
            logger.debug("progress message cleanup failed for job %s", job_id, exc_info=True)

    async def _send(self, chat_id: int, text: str) -> bool:
        try:
            await self.bot.send_message(chat_id, text)
            return True
        except Exception:
            logger.exception("telegram send to chat %s failed", chat_id)
            return False

    async def _send_all(self, chat_id: int, message: str) -> bool:
        """Send every chunk; report success only if all of them landed."""
        for chunk in split_message(message):
            if not await self._send(chat_id, chunk):
                return False
        return True

    async def run_forever(self) -> None:
        while True:
            try:
                await self.poll_once()
            except Exception:
                logger.exception("notification sweep failed")
            await asyncio.sleep(self.poll_interval_seconds)
