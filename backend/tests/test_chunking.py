import numpy as np
import pytest
from sokhan.core.chunking import chunk_samples

SR = 16000


def samples_for(seconds):
    return np.zeros(int(seconds * SR), dtype=np.float32)


def test_empty_samples_produce_no_chunks():
    assert chunk_samples(np.zeros(0, dtype=np.float32), SR) == []


def test_short_audio_is_single_chunk():
    chunks = chunk_samples(samples_for(5), SR)
    assert len(chunks) == 1
    assert chunks[0].start == 0.0
    assert abs(chunks[0].end - 5.0) < 1e-6


def test_long_audio_windows_overlap_and_cover():
    chunks = chunk_samples(samples_for(75), SR, window_seconds=30, overlap_seconds=1)
    assert chunks[0].start == 0.0
    for first, second in zip(chunks, chunks[1:], strict=False):
        assert abs(second.start - (first.start + 29)) < 1e-6
    assert abs(chunks[-1].end - 75.0) < 1e-6
    assert chunks[0].samples.shape[0] == 30 * SR


def test_tiny_tail_folds_into_previous_chunk():
    # 0.9 s of tail after the first window folds into it instead of
    # producing a 0.9 second sliver.
    chunks = chunk_samples(samples_for(30.9), SR, window_seconds=30, overlap_seconds=1)
    assert len(chunks) == 1
    assert abs(chunks[-1].end - 30.9) < 1e-6
    assert chunks[-1].samples.shape[0] == int(30.9 * SR)


def test_short_but_not_tiny_tail_stays_own_chunk():
    chunks = chunk_samples(samples_for(31.5), SR, window_seconds=30, overlap_seconds=1)
    assert len(chunks) == 2
    assert abs(chunks[1].start - 29.0) < 1e-6
    assert abs(chunks[1].end - 31.5) < 1e-6


def test_invalid_overlap_rejected():
    with pytest.raises(ValueError):
        chunk_samples(samples_for(10), SR, window_seconds=1, overlap_seconds=1)
