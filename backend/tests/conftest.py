"""Shared fixtures: per-test SQLite database, API client and a seeded user."""

import io
import os
import sys
import wave

import numpy as np
import pytest

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import sokhan.db as db  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sokhan.auth import generate_token, hash_password, token_hash  # noqa: E402
from sokhan.main import create_app  # noqa: E402
from sokhan.models import User  # noqa: E402


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CELERY_ENABLED", "false")
    monkeypatch.setenv("SUMMARY_ENABLED", "false")
    monkeypatch.setenv("FREE_MINUTES_PER_USER_PER_MONTH", "30")

    from sokhan.config import get_settings

    get_settings.cache_clear()
    db.reset()
    db.configure(f"sqlite:///{tmp_path / 'test.sqlite3'}")
    db.create_all()
    yield create_app()
    db.reset()
    get_settings.cache_clear()


@pytest.fixture()
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def seeded_user(app):
    """A user created directly in the database (no HTTP roundtrip)."""
    token = generate_token()
    with db.session_scope() as session:
        user = User(
            email="sara@example.com",
            password_hash=hash_password("parool-1234"),
            token_hash=token_hash(token),
        )
        session.add(user)
        session.flush()
        user_id = user.id
    return {"token": token, "id": user_id}


@pytest.fixture()
def auth(seeded_user):
    return {"Authorization": f"Bearer {seeded_user['token']}"}


def make_wav_bytes(seconds=2.0, rate=16000):
    t = np.linspace(0, seconds, int(seconds * rate), endpoint=False)
    frames = (np.sin(2 * np.pi * 440.0 * t) * 32000).astype("<i2").tobytes()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(frames)
    return buffer.getvalue()


@pytest.fixture()
def wav_bytes():
    return make_wav_bytes(2.0)


@pytest.fixture()
def fake_engine(monkeypatch):
    """Swap the real Whisper engine for the deterministic test double."""
    from sokhan.core.transcribe import FakeTranscriber

    monkeypatch.setattr(
        "sokhan.worker.pipeline.get_transcriber", lambda: FakeTranscriber()
    )


@pytest.fixture()
def wait_for_job():
    def _wait(client, headers, job_id, timeout_seconds=20):
        import time

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            response = client.get(f"/jobs/{job_id}", headers=headers)
            if response.status_code == 200:
                body = response.json()
                if body["status"] in ("completed", "failed"):
                    return body
            time.sleep(0.2)
        raise AssertionError("job did not finish in time")

    return _wait
