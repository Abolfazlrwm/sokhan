import io
import shutil
from pathlib import Path

import pytest
from docx import Document


def _upload(client, headers, wav_bytes, filename="جلسه-هفته.wav", **fields):
    data = {"language": "fa", "want_summary": "false"}
    data.update(fields)
    return client.post(
        "/jobs",
        files={"file": (filename, wav_bytes, "audio/wav")},
        data=data,
        headers=headers,
    )


def test_upload_run_and_download(client, auth, wav_bytes, wait_for_job, fake_engine):
    response = _upload(client, auth, wav_bytes)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "queued"

    detail = wait_for_job(client, auth, body["id"])
    assert detail["status"] == "completed"
    assert detail["progress"] == 100.0
    # punctuation restoration: the fake engine's plain words now carry a
    # sentence-final period, and search still matches the phrase without it.
    assert "سلام بر تو." in detail["text"]

    txt = client.get(f"/jobs/{body['id']}/transcript?format=txt", headers=auth)
    assert txt.status_code == 200
    assert txt.text == "سلام بر تو."

    srt = client.get(f"/jobs/{body['id']}/transcript?format=srt", headers=auth)
    assert srt.status_code == 200
    assert "00:00:00,000 --> " in srt.text

    docx = client.get(f"/jobs/{body['id']}/transcript?format=docx", headers=auth)
    assert docx.status_code == 200
    document = Document(io.BytesIO(docx.content))
    assert any("سلام بر تو" in p.text for p in document.paragraphs)


def test_transcript_before_completion_conflicts(client, auth, wav_bytes, fake_engine):
    response = _upload(client, auth, wav_bytes)
    job_id = response.json()["id"]

    detail = client.get(f"/jobs/{job_id}", headers=auth).json()
    while detail["status"] in ("queued", "processing"):
        detail = client.get(f"/jobs/{job_id}", headers=auth).json()
    assert detail["status"] == "completed"

    listed = client.get("/jobs", headers=auth).json()
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == job_id


def test_segments_and_new_exports_expose_timestamps(
    client, auth, wav_bytes, wait_for_job, fake_engine
):
    response = _upload(client, auth, wav_bytes)
    job_id = response.json()["id"]
    detail = wait_for_job(client, auth, job_id)

    assert detail["status"] == "completed"
    segments = detail["segments"]
    assert len(segments) >= 1
    assert segments[0]["position"] == 1
    assert segments[0]["start"] == 0.0
    assert "سلام بر تو" in segments[0]["text"]
    # The engine's exp(avg_logprob) flows through to the API and the JSON export.
    assert segments[0]["confidence"] == 0.819

    vtt = client.get(f"/jobs/{job_id}/transcript?format=vtt", headers=auth)
    assert vtt.status_code == 200
    assert "text/vtt" in vtt.headers["content-type"]
    assert vtt.text.startswith("WEBVTT")
    assert "00:00:00.000 --> " in vtt.text

    payload = client.get(f"/jobs/{job_id}/transcript?format=json", headers=auth)
    assert payload.status_code == 200
    body = payload.json()
    assert body["filename"].endswith(".wav")
    assert body["language"] == "fa"
    assert len(body["segments"]) == len(segments)
    assert body["segments"][0]["start"] == 0.0
    assert body["segments"][0]["confidence"] == 0.819
    assert "سلام بر تو" in body["text"]

    bad = client.get(f"/jobs/{job_id}/transcript?format=yaml", headers=auth)
    assert bad.status_code == 422


def test_low_confidence_segments_are_flagged_for_review(
    client, auth, wav_bytes, wait_for_job, monkeypatch
):
    from sokhan.core.transcribe import Segment

    class UnsureTranscriber:
        def transcribe(self, samples, sample_rate, language):
            return [Segment(start=0.0, end=1.0, text="یک جمله نامطمئن", avg_logprob=-1.6, confidence=0.2)]

    monkeypatch.setattr(
        "sokhan.worker.pipeline.get_transcriber", lambda: UnsureTranscriber()
    )

    response = _upload(client, auth, wav_bytes)
    job_id = response.json()["id"]
    detail = wait_for_job(client, auth, job_id)

    assert detail["status"] == "completed"
    assert detail["segments"][0]["confidence"] == 0.2

    srt = client.get(f"/jobs/{job_id}/transcript?format=srt", headers=auth)
    assert "⚠ یک جمله نامطمئن" in srt.text


def test_upload_rejects_corrupt_file(client, auth):
    response = client.post(
        "/jobs",
        files={"file": ("broken.wav", b"this is not audio", "audio/wav")},
        data={"language": "fa"},
        headers=auth,
    )
    assert response.status_code == 422


def _user_id(headers):
    from sokhan.auth import token_hash
    from sokhan.db import session_scope
    from sokhan.models import User

    token = headers["Authorization"].split(" ", 1)[1]
    with session_scope() as session:
        user = session.query(User).filter_by(token_hash=token_hash(token)).one()
        return user.id


def test_upload_402_when_quota_exhausted(client, auth, wav_bytes):
    from sokhan.db import session_scope
    from sokhan.models import Usage

    with session_scope() as session:
        session.add(Usage(user_id=_user_id(auth), job_id=None, seconds=30 * 60))

    response = _upload(client, auth, wav_bytes)
    assert response.status_code == 402
    assert response.json()["detail"]["code"] == "quota_exceeded"


def test_summary_flows_through_job(client, auth, wav_bytes, wait_for_job, fake_engine, monkeypatch):
    class FixedSummarizer:
        def summarize(self, text):
            return "خلاصهٔ آزمایشی سه‌خطی."

    monkeypatch.setattr("sokhan.worker.pipeline.get_summarizer", lambda: FixedSummarizer())

    response = _upload(client, auth, wav_bytes, want_summary="true")
    job_id = response.json()["id"]
    detail = wait_for_job(client, auth, job_id)

    assert detail["status"] == "completed"
    assert detail["summary"] == "خلاصهٔ آزمایشی سه‌خطی."

    endpoint = client.get(f"/jobs/{job_id}/summary", headers=auth)
    assert endpoint.status_code == 200
    assert endpoint.json()["summary"] == "خلاصهٔ آزمایشی سه‌خطی."


def test_delete_job_removes_it(client, auth, wav_bytes, wait_for_job, fake_engine):
    response = _upload(client, auth, wav_bytes)
    job_id = response.json()["id"]
    wait_for_job(client, auth, job_id)

    deleted = client.delete(f"/jobs/{job_id}", headers=auth)
    assert deleted.status_code == 204

    gone = client.get(f"/jobs/{job_id}", headers=auth)
    assert gone.status_code == 404


def test_other_users_cannot_read_a_job(client, auth, wav_bytes, fake_engine):
    response = _upload(client, auth, wav_bytes)
    job_id = response.json()["id"]

    other = client.post("/auth/register", json={"email": "other@example.com", "password": "parool-1234"})
    headers = {"Authorization": f"Bearer {other.json()['api_token']}"}

    assert client.get(f"/jobs/{job_id}", headers=headers).status_code == 404
    assert client.get("/jobs", headers=headers).json()["total"] == 0


def _make_data_dir_unwritable(tmp_path):
    """Replace DATA_DIR with a plain file, so creating DATA_DIR/audio fails."""
    shutil.rmtree(tmp_path / "data")
    (tmp_path / "data").write_text("not a directory")


def test_upload_answers_503_when_storage_is_unwritable(
    client, auth, wav_bytes, fake_engine, tmp_path
):
    _make_data_dir_unwritable(tmp_path)

    response = _upload(client, auth, wav_bytes)

    assert response.status_code == 503
    assert response.json() == {"detail": "upload storage is unavailable, try again later"}
    # No job row is left behind for an upload that was never stored.
    assert client.get("/jobs", headers=auth).json()["total"] == 0


def test_openai_endpoint_answers_503_when_storage_is_unwritable(
    client, auth, wav_bytes, fake_engine, tmp_path
):
    _make_data_dir_unwritable(tmp_path)

    response = client.post(
        "/v1/audio/transcriptions",
        files={"file": ("test.wav", wav_bytes, "audio/wav")},
        data={"language": "fa", "response_format": "json"},
        headers=auth,
    )

    assert response.status_code == 503


def test_failed_write_removes_the_partial_file(app, tmp_path, monkeypatch):
    from sokhan.core.audio import StorageUnavailableError, audio_dir, save_upload

    def write_fails_midway(self, data):
        self.open("wb").write(data[:1])
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(Path, "write_bytes", write_fails_midway)

    with pytest.raises(StorageUnavailableError):
        save_upload(b"RIFF....", "job-1", "clip.wav")
    assert list(audio_dir().iterdir()) == []
