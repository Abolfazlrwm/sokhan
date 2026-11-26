"""Push notifications when tracked jobs finish.

When the bot receives a voice message it says "as soon as it is ready, I
will send you the text" — this worker keeps that promise. Every few
seconds it polls the jobs the store is tracking and, the moment a job
completes, pushes the transcript (split into Telegram-sized chunks); a
failed job gets an apology instead. The backend always keeps working even
if the bot process dies and comes back, because the watch list is
persisted in the token store.

The decision logic lives in module-level functions so tests need neither
aiogram nor a network.
"""

import asyncio
import logging
import time

from aiogram import Bot

from sokhan_bot import texts
from sokhan_bot.client import AuthError, SokhanClient
from sokhan_bot.split import split_message
from sokhan_bot.store import TokenStore

logger = logging.getLogger(__name__)

# After this long a job is presumed stuck; we stop watching it.
GIVE_UP_SECONDS = 6 * 3600


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
                continue

            delivered = await self._send_all(chat_id, message)
            if delivered:
                self.store.untrack(job_id)

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
