"""Merge per-chunk segments into one clean transcript timeline.

Whisper re-hears `overlap` seconds at every chunk boundary, so duplicated
boundary phrases must be dropped and chunk-local timestamps must be shifted
into file-global time. Timestamps that would run before the start or past the
end of the audio are clamped so SRT output is always valid.
"""

from difflib import SequenceMatcher

from sokhan.core.transcribe import Segment

SIMILARITY_THRESHOLD = 0.8
MIN_SEGMENT_SECONDS = 0.05


def offset_segments(segments: list[Segment], offset_seconds: float) -> list[Segment]:
    """Shift chunk-local timestamps into file-global time."""
    if offset_seconds == 0:
        return list(segments)
    return [
        Segment(
            start=segment.start + offset_seconds,
            end=segment.end + offset_seconds,
            text=segment.text,
            avg_logprob=segment.avg_logprob,
            speaker=segment.speaker,
        )
        for segment in segments
    ]


def _texts_similar(left: str, right: str) -> bool:
    return SequenceMatcher(None, left, right).ratio() >= SIMILARITY_THRESHOLD


def _drop_boundary_duplicate(
    merged: list[Segment], incoming: list[Segment], overlap_seconds: float
) -> list[Segment]:
    """Drop a duplicated first segment of a chunk when it repeats merged text.

    `merged` holds all confirmed segments; `incoming` is the next chunk's
    offset segments. If the incoming chunk starts inside the overlap window
    and says roughly the same thing as the last confirmed segment, keep the
    higher-confidence variant and return the remainder to append.
    """
    if not merged or not incoming or overlap_seconds <= 0:
        return incoming
    boundary = merged[-1].end
    window_start = boundary - overlap_seconds
    first = incoming[0]
    if not (window_start <= first.start < boundary):
        return incoming
    if not _texts_similar(merged[-1].text, first.text):
        return incoming
    if first.avg_logprob > merged[-1].avg_logprob:
        # The re-heard variant is more confident: replace the original.
        merged.pop()
        return incoming
    return incoming[1:]


def merge_chunks(
    chunk_segments: list[list[Segment]],
    chunk_starts: list[float],
    overlap_seconds: float,
    total_duration: float | None = None,
) -> list[Segment]:
    """Offset each chunk, drop boundary duplicates and clamp timestamps.

    `chunk_starts[i]` is the file-global offset of chunk i.
    """
    if len(chunk_segments) != len(chunk_starts):
        raise ValueError("chunk_segments and chunk_starts must have the same length")

    merged: list[Segment] = []
    for segments, start in zip(chunk_segments, chunk_starts, strict=True):
        shifted = offset_segments(segments, start)
        shifted = _drop_boundary_duplicate(merged, shifted, overlap_seconds)
        merged.extend(shifted)

    result: list[Segment] = []
    for segment in sorted(merged, key=lambda item: (item.start, item.end)):
        start = max(0.0, segment.start)
        end = segment.end
        if total_duration is not None:
            end = min(end, total_duration)
        if end - start < MIN_SEGMENT_SECONDS:
            continue
        result.append(
            Segment(
                start=round(start, 3),
                end=round(end, 3),
                text=segment.text,
                avg_logprob=segment.avg_logprob,
                speaker=segment.speaker,
            )
        )
    return result
