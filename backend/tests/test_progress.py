"""Job progress moves while a chunk is being decoded, not only between chunks.

A clip shorter than the 30 s window is a single chunk, so chunk-level
progress alone sat at 0% for the whole job and then jumped to 100%.
"""

import sokhan.db as db
from sokhan.core.transcribe import FakeTranscriber, Segment, reports_progress
from sokhan.models import Job


class SlowEngine:
    """Reports four steps through the chunk and records what the DB shows."""

    reports_progress = True

    def __init__(self) -> None:
        self.seen: list[float] = []

    def transcribe(self, samples, sample_rate, language, on_progress=None):
        for fraction in (0.25, 0.5, 0.75, 1.0):
            on_progress(fraction)
            with db.session_scope() as other:
                job = other.query(Job).one()
                self.seen.append(job.progress)
        return [Segment(start=0.0, end=1.0, text="سلام")]


class PlainEngine:
    """A third-party engine with the original three-argument signature."""

    def transcribe(self, samples, sample_rate, language):
        return [Segment(start=0.0, end=1.0, text="سلام")]


def _upload(client, auth, wav_bytes):
    response = client.post(
        "/jobs",
        files={"file": ("clip.wav", wav_bytes, "audio/wav")},
        data={"language": "fa"},
        headers=auth,
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_progress_is_saved_inside_a_single_chunk(
    client, auth, wav_bytes, wait_for_job, monkeypatch
):
    engine = SlowEngine()
    monkeypatch.setattr("sokhan.worker.pipeline.get_transcriber", lambda: engine)
    ticks = iter(range(0, 1000, 2))  # every call is 2 s later: never throttled
    monkeypatch.setattr("sokhan.worker.pipeline._progress_clock", lambda: float(next(ticks)))

    job_id = _upload(client, auth, wav_bytes)
    wait_for_job(client, auth, job_id)

    assert engine.seen == sorted(engine.seen)
    assert 0 < engine.seen[0] < engine.seen[-1] <= 99.0
    assert client.get(f"/jobs/{job_id}", headers=auth).json()["progress"] == 100.0


def test_progress_writes_are_throttled(client, auth, wav_bytes, wait_for_job, monkeypatch):
    engine = SlowEngine()
    monkeypatch.setattr("sokhan.worker.pipeline.get_transcriber", lambda: engine)
    monkeypatch.setattr("sokhan.worker.pipeline._progress_clock", lambda: 5.0)

    wait_for_job(client, auth, _upload(client, auth, wav_bytes))

    # Same instant for every report: only the first one reaches the database.
    assert len(set(engine.seen)) == 1


def test_engines_without_progress_support_still_work(
    client, auth, wav_bytes, wait_for_job, monkeypatch
):
    assert not reports_progress(PlainEngine())
    monkeypatch.setattr("sokhan.worker.pipeline.get_transcriber", lambda: PlainEngine())

    job_id = _upload(client, auth, wav_bytes)

    assert wait_for_job(client, auth, job_id)["status"] == "completed"


def test_fake_engine_reports_fractions_up_to_the_end():
    seen: list[float] = []
    import numpy as np

    FakeTranscriber().transcribe(np.zeros(16000 * 4, dtype=np.float32), 16000, "fa", seen.append)

    assert seen == sorted(seen) and seen[-1] == 1.0
