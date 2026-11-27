"""Notification and live-progress logic — fakes only, no aiogram or network."""

import asyncio

from aiogram.exceptions import TelegramBadRequest
from sokhan_bot.notify import (
    BAR_CELLS,
    CompletionNotifier,
    completion_message,
    progress_bar,
    progress_message,
)
from sokhan_bot.store import TokenStore


def test_completed_job_returns_transcript_text():
    message = completion_message({"status": "completed", "text": "سلام بر تو"})
    assert message is not None
    assert "سلام بر تو" in message


def test_failed_job_returns_failure_notice():
    message = completion_message({"status": "failed", "error": "decode error"})
    assert message is not None
    assert "decode error" in message


def test_running_jobs_wait():
    assert completion_message({"status": "queued"}) is None
    assert completion_message({"status": "processing"}) is None


def test_completed_job_without_text_gets_placeholder():
    message = completion_message({"status": "completed", "text": ""})
    assert message is not None
    # No transcript means the placeholder text, not an empty message.
    assert len(message) > 10


def test_failed_job_without_error_still_renders():
    message = completion_message({"status": "failed", "error": None})
    assert message is not None


# --- live progress rendering -------------------------------------------------


def test_progress_bar_fills_and_pads():
    assert progress_bar(0) == "░" * BAR_CELLS
    assert progress_bar(100) == "▓" * BAR_CELLS
    assert progress_bar(42) == "▓" * 4 + "░" * 6
    assert progress_bar(-5) == "░" * BAR_CELLS  # underflow clamps to empty
    assert progress_bar(999) == "▓" * BAR_CELLS  # overflow clamps to full


def test_progress_message_renders_id_bar_and_persian_status():
    message = progress_message({"id": "abc123", "status": "processing", "progress": 33.3})
    assert "شناسهٔ پردازش: abc123" in message
    assert "۳۳٪" in message  # Persian numerals
    assert "در حال پردازش" in message  # Persian status label
    assert "▓▓▓" in message and "░" * 7 in message


def test_progress_message_defaults_for_missing_fields():
    message = progress_message({})
    assert "شناسهٔ پردازش: —" in message
    assert "۰٪" in message
    assert "در صف" in message


# --- poll_once behaviour with fakes ------------------------------------------


class FakeBot:
    def __init__(self):
        self.sent = []
        self.edits = []
        self.deleted = []

    async def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))

    async def edit_message_text(self, text, chat_id=None, message_id=None):
        self.edits.append((chat_id, message_id, text))

    async def delete_message(self, chat_id, message_id):
        self.deleted.append((chat_id, message_id))


class FakeClient:
    def __init__(self, jobs):
        self.jobs = jobs

    def get_job(self, token, job_id):
        return self.jobs[job_id]


def _notifier(store, client, bot):
    return CompletionNotifier(bot, client, store, poll_interval_seconds=0.0)


def test_poll_once_edits_live_progress_then_delivers(tmp_path):
    store = TokenStore(str(tmp_path / "store.json"))
    store.set(7, "token")
    store.track("j1", 7, message_id=100, progress=0.0, status="queued")
    bot = FakeBot()
    client = FakeClient({"j1": {"id": "j1", "status": "processing", "progress": 50.0}})
    notifier = _notifier(store, client, bot)

    asyncio.run(notifier.poll_once())
    assert len(bot.edits) == 1
    assert "۵۰٪" in bot.edits[0][2]
    assert "در حال پردازش" in bot.edits[0][2]

    # Same percent and status again: no redundant edit is sent to Telegram.
    asyncio.run(notifier.poll_once())
    assert len(bot.edits) == 1

    # Completion deletes the progress message and pushes the transcript.
    client.jobs["j1"] = {"id": "j1", "status": "completed", "progress": 100.0, "text": "سلام بر تو"}
    asyncio.run(notifier.poll_once())
    assert bot.deleted == [(7, 100)]
    assert bot.sent and "سلام بر تو" in bot.sent[-1][1]
    assert store.watch("j1") is None


def test_poll_once_without_message_id_skips_live_edits(tmp_path):
    """Watches recorded by older bot versions get completion only."""
    store = TokenStore(str(tmp_path / "store.json"))
    store.set(7, "token")
    store.track("j2", 7)  # no message_id
    bot = FakeBot()
    client = FakeClient({"j2": {"id": "j2", "status": "processing", "progress": 10.0}})
    notifier = _notifier(store, client, bot)

    asyncio.run(notifier.poll_once())
    assert bot.edits == []

    client.jobs["j2"] = {"id": "j2", "status": "completed", "progress": 100.0, "text": "متن"}
    asyncio.run(notifier.poll_once())
    assert bot.deleted == []  # nothing to clean up
    assert bot.sent and "متن" in bot.sent[-1][1]
    assert store.watch("j2") is None


def test_poll_once_survives_a_deleted_progress_message(tmp_path):
    """A user-deleted progress message stops edits but not the delivery."""
    store = TokenStore(str(tmp_path / "store.json"))
    store.set(7, "token")
    store.track("j3", 7, message_id=200, progress=0.0, status="queued")
    bot = FakeBot()
    client = FakeClient({"j3": {"id": "j3", "status": "processing", "progress": 20.0}})
    notifier = _notifier(store, client, bot)

    async def boom(text, chat_id=None, message_id=None):
        raise TelegramBadRequest(method=None, message="message to edit not found")

    bot.edit_message_text = boom
    asyncio.run(notifier.poll_once())
    assert store.watch("j3").get("message_id") is None

    client.jobs["j3"] = {"id": "j3", "status": "completed", "progress": 100.0, "text": "متن"}
    asyncio.run(notifier.poll_once())
    assert bot.sent and "متن" in bot.sent[-1][1]
