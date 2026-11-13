from sokhan.core.transcribe import FakeTranscriber


def _upload_and_wait(client, auth, wav_bytes, wait_for_job, filename):
    response = client.post(
        "/jobs",
        files={"file": (filename, wav_bytes, "audio/wav")},
        data={"language": "fa"},
        headers=auth,
    )
    job_id = response.json()["id"]
    return wait_for_job(client, auth, job_id)


def test_search_matches_transcript_text(client, auth, wav_bytes, wait_for_job, monkeypatch):
    monkeypatch.setattr("sokhan.worker.pipeline.get_transcriber", lambda: FakeTranscriber())
    detail = _upload_and_wait(client, auth, wav_bytes, wait_for_job, "voice.wav")

    found = client.get("/search", params={"q": "سلام"}, headers=auth).json()
    assert found["total"] == 1
    assert found["items"][0]["id"] == detail["id"]

    nothing = client.get("/search", params={"q": "چیزی‌که نیست"}, headers=auth).json()
    assert nothing["total"] == 0


def test_search_matches_filename(client, auth, wav_bytes, wait_for_job, monkeypatch):
    monkeypatch.setattr("sokhan.worker.pipeline.get_transcriber", lambda: FakeTranscriber())
    detail = _upload_and_wait(client, auth, wav_bytes, wait_for_job, "کلاس-ریاضی.wav")

    found = client.get("/search", params={"q": "ریاضی"}, headers=auth).json()
    assert found["total"] == 1
    assert found["items"][0]["id"] == detail["id"]


def test_search_normalizes_arabic_code_points(client, auth, wav_bytes, wait_for_job, monkeypatch):
    monkeypatch.setattr("sokhan.worker.pipeline.get_transcriber", lambda: FakeTranscriber())
    _upload_and_wait(client, auth, wav_bytes, wait_for_job, "voice.wav")

    # Query typed with Arabic yeh must still match Persian text.
    found = client.get("/search", params={"q": "بر تو"}, headers=auth)
    assert found.status_code == 200
    assert found.json()["total"] >= 1
