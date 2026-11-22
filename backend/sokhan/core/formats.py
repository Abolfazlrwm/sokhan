"""Export formats: plain text, SRT/VTT subtitles, JSON and DOCX documents."""

import io
import json
from collections.abc import Sequence
from typing import Protocol

from docx import Document


class TranscriptLike(Protocol):
    """Anything with segment fields — core segments and DB rows both qualify."""

    start: float
    end: float
    text: str
    speaker: str | None
    confidence: float | None


# Prefix/suffix marking segments the model itself was unsure about (see
# `low_confidence_below` on the exporters). A plain text glyph, kept out of
# the way of subtitle players and Word reviews alike.
REVIEW_MARK = "⚠"


def _review_prefix(confidence: float | None, low_confidence_below: float | None) -> str:
    flagged = (
        low_confidence_below is not None
        and confidence is not None
        and confidence < low_confidence_below
    )
    return f"{REVIEW_MARK} " if flagged else ""


def format_srt_timestamp(seconds: float) -> str:
    """Render seconds as an SRT timecode (HH:MM:SS,mmm).

    Negative values clamp to zero so a stray Whisper timestamp can never
    produce an invalid subtitle.
    """
    total_ms = int(round(max(0.0, seconds) * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def to_txt(segments: Sequence[TranscriptLike]) -> str:
    """Plain transcript: one segment per line, in order."""
    return "\n".join(segment.text for segment in segments).strip()


def to_srt(
    segments: Sequence[TranscriptLike],
    *,
    low_confidence_below: float | None = None,
) -> str:
    """SubRip subtitles with one numbered block per segment.

    Segments whose `confidence` falls below `low_confidence_below` get a `⚠`
    prefix so human reviewers spot them in the player.
    """
    blocks: list[str] = []
    for position, segment in enumerate(segments, start=1):
        start = format_srt_timestamp(segment.start)
        end = format_srt_timestamp(segment.end)
        text = segment.text.replace("\r", " ").strip() or "..."
        speaker_prefix = f"[{segment.speaker}] " if segment.speaker else ""
        review = _review_prefix(segment.confidence, low_confidence_below)
        blocks.append(f"{position}\n{start} --> {end}\n{speaker_prefix}{review}{text}\n")
    return "\n".join(blocks)


def format_vtt_timestamp(seconds: float) -> str:
    """Render seconds as a WebVTT timecode (HH:MM:SS.mmm — dot milliseconds)."""
    return format_srt_timestamp(seconds).replace(",", ".")


def to_vtt(
    segments: Sequence[TranscriptLike],
    *,
    low_confidence_below: float | None = None,
) -> str:
    """WebVTT subtitles; speakers use the VTT voice tag."""
    lines = ["WEBVTT", ""]
    for segment in segments:
        start = format_vtt_timestamp(segment.start)
        end = format_vtt_timestamp(segment.end)
        text = segment.text.replace("\r", " ").strip() or "..."
        voice = f"<v {segment.speaker}> " if segment.speaker else ""
        review = _review_prefix(segment.confidence, low_confidence_below)
        lines.append(f"{start} --> {end}")
        lines.append(f"{voice}{review}{text}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def to_json_transcript(
    segments: Sequence[TranscriptLike],
    *,
    filename: str = "",
    language: str = "",
    duration_seconds: float = 0.0,
) -> str:
    """Machine-readable transcript: metadata plus one object per segment.

    Each segment carries its `confidence` (the model's exp(avg_logprob),
    rounded to three decimals, or null) so downstream tools can rank spans
    for human review themselves.
    """
    payload = {
        "filename": filename,
        "language": language,
        "duration_seconds": round(max(0.0, duration_seconds), 3),
        "text": to_txt(segments),
        "segments": [
            {
                "position": position,
                "start": segment.start,
                "end": segment.end,
                "speaker": segment.speaker,
                "confidence": (
                    round(segment.confidence, 3) if segment.confidence is not None else None
                ),
                "text": segment.text,
            }
            for position, segment in enumerate(segments, start=1)
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def to_docx(
    segments: Sequence[TranscriptLike],
    title: str = "Transcript",
    *,
    low_confidence_below: float | None = None,
) -> bytes:
    """Word document with a heading and one paragraph per segment."""
    document = Document()
    document.add_heading(title, level=1)
    for segment in segments:
        timecode = format_srt_timestamp(segment.start)[:-4]  # HH:MM:SS
        prefix = f"[{segment.speaker}] " if segment.speaker else ""
        review = _review_prefix(segment.confidence, low_confidence_below)
        document.add_paragraph(f"{timecode}  {prefix}{review}{segment.text}")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
