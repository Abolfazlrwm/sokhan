import pytest
from sokhan.core.transcribe import FakeTranscriber
from sokhan.db import session_scope
from sokhan.models import Usage


def _headers(seeded_user):
    return {"Authorization": f"Bearer {seeded_user['token']}"}


def _post(client, seeded_user, wav_bytes, **overrides):
    data = {"language": "fa", "response_format": "json"}
    data.update(overrides)
    return client.post(
        "/v1/audio/transcriptions",
        files={"file": ("test.wav", wav_bytes, "audio/wav")},
        data=data,
        headers=_headers(seeded_user),
    )


def test_transcriptions_json_with_fake_engine(client, seeded_user, wav_bytes, monkeypatch):
    monkeypatch.setattr("sokhan.api.routes_openai.get_transcriber", lambda: FakeTranscriber())

    response = _post(client, seeded_user, wav_bytes)

    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "سلام بر تو"
    assert body["model"].startswith("whisper-")


def test_transcriptions_text_format(client, seeded_user, wav_bytes, monkeypatch):
    monkeypatch.setattr("sokhan.api.routes_openai.get_transcriber", lambda: FakeTranscriber())

    response = _post(client, seeded_user, wav_bytes, response_format="text")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert response.text == "سلام بر تو"


def test_transcriptions_srt_format(client, seeded_user, wav_bytes, monkeypatch):
    monkeypatch.setattr("sokhan.api.routes_openai.get_transcriber", lambda: FakeTranscriber())

    response = _post(client, seeded_user, wav_bytes, response_format="srt")

    assert response.status_code == 200
    assert "00:00:00,000 --> " in response.text
    assert "سلام بر تو" in response.text


def test_transcriptions_verbose_json(client, seeded_user, wav_bytes, monkeypatch):
    monkeypatch.setattr("sokhan.api.routes_openai.get_transcriber", lambda: FakeTranscriber())

    response = _post(client, seeded_user, wav_bytes, response_format="verbose_json")
    body = response.json()

    assert body["language"] == "fa"
    assert body["duration"] == pytest.approx(2.0, abs=0.2)
    assert len(body["segments"]) == 1
    assert body["segments"][0]["text"] == "سلام بر تو"


def test_transcriptions_requires_token(client, wav_bytes):
    response = client.post(
        "/v1/audio/transcriptions",
        files={"file": ("test.wav", wav_bytes, "audio/wav")},
    )
    assert response.status_code == 401


def test_transcriptions_rejects_unknown_response_format(client, seeded_user, wav_bytes):
    response = _post(client, seeded_user, wav_bytes, response_format="xml")
    assert response.status_code == 422


def test_transcriptions_rejects_empty_file(client, seeded_user):
    response = client.post(
        "/v1/audio/transcriptions",
        files={"file": ("test.wav", b"", "audio/wav")},
        data={"language": "fa"},
        headers=_headers(seeded_user),
    )
    assert response.status_code == 422


def test_transcriptions_returns_402_when_quota_exhausted(client, seeded_user, wav_bytes, monkeypatch):
    monkeypatch.setattr("sokhan.api.routes_openai.get_transcriber", lambda: FakeTranscriber())
    with session_scope() as session:
        session.add(Usage(user_id=seeded_user["id"], job_id=None, seconds=30 * 60))

    response = _post(client, seeded_user, wav_bytes)

    assert response.status_code == 402
    assert response.json()["detail"]["code"] == "quota_exceeded"


def test_transcriptions_records_usage(client, seeded_user, wav_bytes, monkeypatch):
    monkeypatch.setattr("sokhan.api.routes_openai.get_transcriber", lambda: FakeTranscriber())

    _post(client, seeded_user, wav_bytes)

    with session_scope() as session:
        total = sum(
            usage.seconds for usage in session.query(Usage).filter_by(user_id=seeded_user["id"])
        )
    assert total == pytest.approx(2.0, abs=0.2)
