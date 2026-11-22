"""Streaming decode: the block decoder, the streaming chunker and the pipeline.

The core property under test: `iter_chunks` over blocks from
`iter_mono_16k_blocks` produces exactly the chunks `chunk_samples` produces
from the full decode — so switching the worker to streaming changes memory
behaviour, not transcription behaviour.
"""

import os
import sys
import wave

import numpy as np
import pytest

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from sokhan.core.audio import (  # noqa: E402
    SAMPLE_RATE,
    decode_to_mono_16k,
    iter_mono_16k_blocks,
    probe_duration_seconds,
)
from sokhan.core.chunking import chunk_samples, iter_chunks  # noqa: E402


def _wav_file(tmp_path, seconds, rate=SAMPLE_RATE):
    """Write a mono 16-bit WAV and return its path (self-contained helper)."""
    t = np.linspace(0, seconds, int(seconds * rate), endpoint=False)
    frames = (np.sin(2 * np.pi * 440.0 * t) * 32000).astype("<i2").tobytes()
    path = tmp_path / "clip.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(frames)
    return path


def _sine(total_samples: int) -> np.ndarray:
    t = np.arange(total_samples, dtype=np.float64)
    return (np.sin(2 * np.pi * 440.0 * t / SAMPLE_RATE) * 0.5).astype(np.float32)


def _split_blocks(samples: np.ndarray, rng: np.random.Generator) -> list[np.ndarray]:
    """Cut `samples` into randomly sized non-empty blocks, like a decoder would."""
    blocks = []
    position = 0
    while position < len(samples):
        size = int(rng.integers(1, max(2, len(samples) // 3 + 1)))
        blocks.append(samples[position : position + size])
        position += size
    return blocks


def _assert_same_chunks(batched, streamed) -> None:
    assert len(batched) == len(streamed)
    for expected, actual in zip(batched, streamed, strict=True):
        # Timestamps derived from integer sample indices: equal to the last ulp.
        assert abs(expected.start - actual.start) < 1e-9
        assert abs(expected.end - actual.end) < 1e-9
        assert np.array_equal(expected.samples, actual.samples)


@pytest.mark.parametrize(
    "seconds",
    [0.0, 0.1, 1.0, 2.0, 2.1, 28.0, 30.0, 30.5, 30.9, 31.0, 31.9, 32.0, 59.0, 60.0, 61.0, 90.5],
)
def test_iter_chunks_matches_chunk_samples(seconds):
    total = int(seconds * SAMPLE_RATE)
    samples = _sine(total)
    batched = chunk_samples(samples, SAMPLE_RATE)
    streamed = list(iter_chunks([samples], SAMPLE_RATE))
    _assert_same_chunks(batched, streamed)


def test_iter_chunks_matches_batch_across_random_block_splits():
    rng = np.random.default_rng(2026)
    for _trial in range(40):
        total = int(rng.uniform(0.0, 75.0) * SAMPLE_RATE)
        samples = _sine(total)
        blocks = _split_blocks(samples, rng)
        _assert_same_chunks(
            chunk_samples(samples, SAMPLE_RATE),
            list(iter_chunks(iter(blocks), SAMPLE_RATE)),
        )


@pytest.mark.parametrize("overlap", [0.0, 1.0, 5.0])
def test_iter_chunks_honours_overlap_knob(overlap):
    samples = _sine(int(45.0 * SAMPLE_RATE))
    _assert_same_chunks(
        chunk_samples(samples, SAMPLE_RATE, overlap_seconds=overlap),
        list(iter_chunks([samples], SAMPLE_RATE, overlap_seconds=overlap)),
    )


def test_iter_chunks_consumes_lazily():
    """The generator must not drain the source to emit its first chunks.

    Streaming decode exists so a 2-hour file never sits in RAM; a chunker
    that pulled every block up front would undo that. With 10-second blocks
    and a 30-second window, exactly four blocks are enough to release the
    first chunk — decisively fewer than the 18 the file holds.
    """
    samples = _sine(int(180.0 * SAMPLE_RATE))
    blocks = [samples[i : i + 10 * SAMPLE_RATE] for i in range(0, len(samples), 10 * SAMPLE_RATE)]
    pulled = []

    def counting():
        for block in blocks:
            pulled.append(block)
            yield block

    streamed = iter_chunks(counting(), SAMPLE_RATE)
    first = next(streamed)
    assert first.start == 0.0
    assert len(pulled) < len(blocks) // 2


def test_iter_mono_16k_blocks_matches_full_decode(tmp_path):
    path = _wav_file(tmp_path, 6.0)

    full = decode_to_mono_16k(str(path))
    streamed = np.concatenate(list(iter_mono_16k_blocks(str(path), block_seconds=1.0)))

    assert streamed.shape == full.shape
    # int16 samples scaled by the same constant: equal within one quantisation step.
    assert np.allclose(streamed, full, atol=1e-6, rtol=0)


def test_iter_mono_16k_blocks_handles_stereo_and_resample(tmp_path):
    """A stereo 44.1 kHz source lands as the same mono 16 kHz signal."""
    rate = 44100
    seconds = 2.0
    t = np.linspace(0, seconds, int(seconds * rate), endpoint=False)
    stereo = np.stack(
        [(np.sin(2 * np.pi * 440.0 * t) * 20000), (np.sin(2 * np.pi * 330.0 * t) * 20000)],
        axis=1,
    ).astype("<i2")
    path = tmp_path / "stereo.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(stereo.tobytes())

    full = decode_to_mono_16k(str(path))
    streamed = np.concatenate(list(iter_mono_16k_blocks(str(path), block_seconds=0.5)))
    assert streamed.shape == full.shape
    assert full.shape[0] == int(seconds * SAMPLE_RATE)
    assert np.allclose(streamed, full, atol=1e-6, rtol=0)


def test_probe_duration_without_full_decode(tmp_path):
    """Headerless garbage never triggers a full decode in streaming mode."""
    garbage = tmp_path / "broken.wav"
    garbage.write_bytes(b"not audio at all")
    assert probe_duration_seconds(str(garbage), allow_full_decode=False) is None

    good = _wav_file(tmp_path, 3.0)
    duration = probe_duration_seconds(str(good), allow_full_decode=False)
    assert duration is not None and abs(duration - 3.0) < 0.05


def test_pipeline_streams_by_default(app, client, auth, wav_bytes, wait_for_job, fake_engine):
    """The default worker path is the streaming one and still completes."""
    response = client.post(
        "/jobs",
        files={"file": ("stream.wav", wav_bytes, "audio/wav")},
        data={"language": "fa"},
        headers=auth,
    )
    assert response.status_code == 201
    detail = wait_for_job(client, auth, response.json()["id"])
    assert detail["status"] == "completed"
    assert detail["progress"] == 100.0
    assert detail["duration_seconds"] == pytest.approx(2.0, abs=0.05)
    assert "سلام بر تو" in detail["text"]


@pytest.fixture()
def legacy_decode(monkeypatch):
    monkeypatch.setenv("STREAMING_DECODE", "false")


def test_pipeline_legacy_full_decode_still_works(
    legacy_decode, app, client, auth, wav_bytes, wait_for_job, fake_engine
):
    """STREAMING_DECODE=false keeps the pre-streaming behaviour intact."""
    response = client.post(
        "/jobs",
        files={"file": ("legacy.wav", wav_bytes, "audio/wav")},
        data={"language": "fa"},
        headers=auth,
    )
    assert response.status_code == 201
    detail = wait_for_job(client, auth, response.json()["id"])
    assert detail["status"] == "completed"
    assert detail["duration_seconds"] == pytest.approx(2.0, abs=0.05)
    assert "سلام بر تو" in detail["text"]
