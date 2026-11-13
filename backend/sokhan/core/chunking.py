"""Split long audio into fixed windows with a small overlap.

The overlap lets the merge step repair words that Whisper would otherwise cut
in half at a window boundary. The full file is decoded to memory first; for
multi-hour recordings this is a conscious trade-off documented in
docs/architecture.md.
"""

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
