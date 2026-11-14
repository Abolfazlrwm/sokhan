"""Tests for the diarization engines, factory and segment labelling."""

import numpy as np
from sokhan.core.transcribe import Segment
from sokhan.diarization import (
    EnergyClusterDiarizer,
    StubDiarizer,
    get_diarizer,
    label_segments,
)
from sokhan.diarization.base import SpeakerTurn

RATE = 16_000


def _tone(seconds: float, freq: float, amplitude: float = 0.4) -> np.ndarray:
    t = np.linspace(0.0, seconds, int(seconds * RATE), endpoint=False)
    return amplitude * np.sin(2 * np.pi * freq * t)


def _two_speakers() -> np.ndarray:
    """A low-pitch voice then a clearly higher-pitch voice, no silence."""
    low = _tone(2.0, 180.0)
    high = _tone(2.0, 420.0)
    noise = np.random.default_rng(3).normal(0.0, 0.005, size=low.size + high.size)
    return np.concatenate([low, high]) + noise


def test_energy_diarizer_separates_two_voices() -> None:
    turns = EnergyClusterDiarizer().diarize(_two_speakers(), RATE)
    assert turns, "two distinct voices must produce turns"
    speakers = {turn.speaker for turn in turns}
    assert speakers == {"SPK_1", "SPK_2"}
    # the second half of the clip belongs to a different speaker than the first
    first_half = {turn.speaker for turn in turns if turn.start < 2.0}
    second_half = {turn.speaker for turn in turns if turn.end > 2.0}
    assert first_half != second_half or len(turns) == 1
    assert first_half and second_half


def test_energy_diarizer_on_silence_then_speech() -> None:
    silence = np.zeros(int(1.2 * RATE))
    voiced = _tone(2.5, 250.0)
    turns = EnergyClusterDiarizer().diarize(np.concatenate([silence, voiced]), RATE)
    assert turns, "a voiced passage must produce at least one turn"
    assert all(turn.start >= 1.0 for turn in turns), "silence must not be labelled"
    assert {turn.speaker for turn in turns} == {"SPK_1"}, "one voice, one label"


def test_energy_diarizer_on_pure_silence() -> None:
    turns = EnergyClusterDiarizer().diarize(np.zeros(int(2.0 * RATE)), RATE)
    assert turns == []


def test_label_segments_by_overlap() -> None:
    segments = [
        Segment(start=0.0, end=2.0, text="اول"),
        Segment(start=2.1, end=4.0, text="دوم"),
        Segment(start=5.0, end=6.0, text="خارج از نوبت"),
    ]
    turns = [
        SpeakerTurn(start=0.0, end=2.0, speaker="SPK_1"),
        SpeakerTurn(start=2.0, end=4.0, speaker="SPK_2"),
    ]
    label_segments(segments, turns)
    assert [segment.speaker for segment in segments] == ["SPK_1", "SPK_2", None]


def test_factory_default_is_stub(monkeypatch) -> None:
    monkeypatch.delenv("DIARIZATION_ENGINE", raising=False)
    from sokhan.config import get_settings

    get_settings.cache_clear()
    try:
        assert isinstance(get_diarizer(), StubDiarizer)
    finally:
        get_settings.cache_clear()


def test_factory_selects_energy(monkeypatch) -> None:
    monkeypatch.setenv("DIARIZATION_ENGINE", "energy")
    from sokhan.config import get_settings

    get_settings.cache_clear()
    try:
        engine = get_diarizer()
        assert isinstance(engine, EnergyClusterDiarizer)
    finally:
        get_settings.cache_clear()


def test_factory_falls_back_when_pyannote_missing(monkeypatch) -> None:
    monkeypatch.setenv("DIARIZATION_ENGINE", "pyannote")
    from sokhan.config import get_settings

    get_settings.cache_clear()
    try:
        engine = get_diarizer()
        assert isinstance(engine, StubDiarizer), "no torch/token must fall back to stub"
    finally:
        get_settings.cache_clear()


def test_pipeline_labels_segments_when_diarizer_present(
    client, auth, wav_bytes, wait_for_job, fake_engine, monkeypatch
) -> None:
    """End-to-end: a working diarizer's labels reach the SRT export."""

    class LoudStub:
        name = "loud-stub"

        def diarize(self, samples: np.ndarray, sample_rate: int) -> list[SpeakerTurn]:
            duration = len(samples) / sample_rate
            return [SpeakerTurn(0.0, duration, "SPK_1")]

    monkeypatch.setattr("sokhan.worker.pipeline.get_diarizer", lambda: LoudStub())

    response = client.post(
        "/jobs",
        files={"file": ("clip.wav", wav_bytes, "audio/wav")},
        data={"language": "fa", "want_summary": "false"},
        headers=auth,
    )
    assert response.status_code == 201
    detail = wait_for_job(client, auth, response.json()["id"])
    assert detail["status"] == "completed"

    srt = client.get(
        f"/jobs/{response.json()['id']}/transcript?format=srt", headers=auth
    )
    assert srt.status_code == 200
    assert "[SPK_1]" in srt.text


def test_pipeline_survives_a_broken_diarizer(
    client, auth, wav_bytes, wait_for_job, fake_engine, monkeypatch
) -> None:
    """A crashing engine must never fail the job — labels are optional."""

    class Exploding:
        name = "exploding"

        def diarize(self, samples: np.ndarray, sample_rate: int) -> list[SpeakerTurn]:
            raise RuntimeError("engine exploded")

    monkeypatch.setattr("sokhan.worker.pipeline.get_diarizer", lambda: Exploding())

    response = client.post(
        "/jobs",
        files={"file": ("clip.wav", wav_bytes, "audio/wav")},
        data={"language": "fa", "want_summary": "false"},
        headers=auth,
    )
    detail = wait_for_job(client, auth, response.json()["id"])
    assert detail["status"] == "completed"
