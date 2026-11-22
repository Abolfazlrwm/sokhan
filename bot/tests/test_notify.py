"""Completion notification logic — pure functions, no aiogram or network."""

from sokhan_bot.notify import completion_message


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
