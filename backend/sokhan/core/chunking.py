"""Split long audio into fixed windows with a small overlap.

The overlap lets the merge step repair words that Whisper would otherwise cut
in half at a window boundary. Two entry points share one behaviour:
`chunk_samples` slices an in-memory array (legacy, and required by the
diarizers), `iter_chunks` consumes a block iterator lazily so the audio can
be decoded while transcribing — peak memory is one window, not the file.
`test_streaming.py` proves the two produce identical chunks.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, replace

import numpy as np

DEFAULT_WINDOW_SECONDS = 30.0
DEFAULT_OVERLAP_SECONDS = 1.0

# Tails shorter than this are folded into the previous chunk instead of
# emitting a tiny sliver that Whisper struggles with.
MIN_TAIL_SECONDS = 2.0


@dataclass(frozen=True)
class Chunk:
    """One window of samples; `start`/`end` are file-global seconds."""

    start: float
    end: float
    samples: np.ndarray

    @property
    def duration(self) -> float:
        return self.end - self.start


def chunk_samples(
    samples: np.ndarray,
    sample_rate: int,
    window_seconds: float = DEFAULT_WINDOW_SECONDS,
    overlap_seconds: float = DEFAULT_OVERLAP_SECONDS,
) -> list[Chunk]:
    """Slice mono samples into overlapping windows covering the whole file."""
    if overlap_seconds < 0 or overlap_seconds >= window_seconds:
        raise ValueError("overlap must be >= 0 and smaller than the window")
    total_samples = len(samples)
    if total_samples == 0:
        return []

    window = int(round(window_seconds * sample_rate))
    overlap = int(round(overlap_seconds * sample_rate))
    step = window - overlap
    if step <= 0:
        raise ValueError("window must be larger than overlap")

    min_tail = int(round(MIN_TAIL_SECONDS * sample_rate))
    chunks: list[Chunk] = []
    start = 0
    while start < total_samples:
        end = min(start + window, total_samples)
        remaining = total_samples - start
        if chunks and remaining < min(min_tail, step + 1):
            # Fold the short tail into the previous chunk (its own samples
            # already include the overlap region, so nothing is lost).
            previous = chunks[-1]
            new_start = int(round(previous.start * sample_rate))
            chunks[-1] = replace(
                previous,
                end=end / sample_rate,
                samples=samples[new_start:end],
            )
            break
        chunks.append(
            Chunk(
                start=start / sample_rate,
                end=end / sample_rate,
                samples=samples[start:end],
            )
        )
        if end == total_samples:
            break
        start += step
    return chunks


def iter_chunks(
    blocks: Iterable[np.ndarray],
    sample_rate: int,
    window_seconds: float = DEFAULT_WINDOW_SECONDS,
    overlap_seconds: float = DEFAULT_OVERLAP_SECONDS,
) -> Iterator[Chunk]:
    """Streaming equivalent of `chunk_samples` over a block iterator.

    `blocks` are float32 mono slices of one long recording (from
    `iter_mono_16k_blocks`). Chunks are emitted as soon as it is safe —
    safe means the successor chunk can no longer be folded into this one,
    which is decided once `threshold` samples exist beyond the successor's
    start. The last chunk therefore carries the same tail-folding behaviour
    as the batch version: a final stretch shorter than MIN_TAIL_SECONDS is
    glued onto the previous window instead of standing alone.
    """
    if overlap_seconds < 0 or overlap_seconds >= window_seconds:
        raise ValueError("overlap must be >= 0 and smaller than the window")
    window = int(round(window_seconds * sample_rate))
    overlap = int(round(overlap_seconds * sample_rate))
    step = window - overlap
    if step <= 0:
        raise ValueError("window must be larger than overlap")
    threshold = min(int(round(MIN_TAIL_SECONDS * sample_rate)), step + 1)

    buf = np.zeros(0, dtype=np.float32)
    buf_start = 0  # global sample index of buf[0]
    next_start = 0  # global sample index where the next chunk begins
    candidate: Chunk | None = None  # built but held until release is safe

    def build() -> None:
        nonlocal candidate, buf, buf_start, next_start
        if candidate is not None or (buf_start + buf.size) - next_start < window:
            return
        offset = next_start - buf_start
        candidate = Chunk(
            start=next_start / sample_rate,
            end=(next_start + window) / sample_rate,
            samples=buf[offset : offset + window],
        )
        next_start += step
        buf = buf[next_start - buf_start :]
        buf_start = next_start

    for block in blocks:
        block = np.asarray(block, dtype=np.float32)
        buf = block if buf.size == 0 else np.concatenate([buf, block])
        build()
        # The chunk after `candidate` folds only if fewer than `threshold`
        # samples would remain for it; once that many have arrived we know
        # it will not, so the candidate is safe to release.
        while candidate is not None and (buf_start + buf.size) - next_start >= threshold:
            yield candidate
            candidate = None
            build()

    total = buf_start + buf.size
    if candidate is not None:
        if total - next_start < threshold:
            # The tail is too short to stand alone: fold it into the
            # candidate, exactly as chunk_samples folds its last chunk.
            # buf starts `overlap` samples after the candidate's window end
            # region, so the non-overlapping tail is buf[overlap:].
            tail = buf[overlap:]
            samples = (
                np.concatenate([candidate.samples, tail]) if tail.size else candidate.samples
            )
            yield replace(
                candidate,
                end=total / sample_rate,
                samples=samples,
            )
            return
        yield candidate
    if buf.size:
        # Whatever remains after the released candidate is at least
        # `threshold` samples (the release rule guarantees it), so the batch
        # chunker over the remainder cannot fold into an already-yielded
        # chunk — its own tail folding stays internal.
        for chunk in chunk_samples(buf, sample_rate, window_seconds, overlap_seconds):
            yield Chunk(
                start=chunk.start + buf_start / sample_rate,
                end=chunk.end + buf_start / sample_rate,
                samples=chunk.samples,
            )
