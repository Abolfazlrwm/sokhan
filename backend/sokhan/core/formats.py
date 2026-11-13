"""Export formats: plain text, SRT subtitles and DOCX documents."""

import io
from collections.abc import Sequence
from typing import Protocol

from docx import Document


class TranscriptLike(Protocol):
    """Anything with segment fields — core segments and DB rows both qualify."""

    start: float
    end: float
    text: str
    speaker: str | None


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


def to_srt(segments: Sequence[TranscriptLike]) -> str:
    """SubRip subtitles with one numbered block per segment."""
    blocks: list[str] = []
    for position, segment in enumerate(segments, start=1):
        start = format_srt_timestamp(segment.start)
        end = format_srt_timestamp(segment.end)
        text = segment.text.replace("\r", " ").strip() or "..."
        speaker_prefix = f"[{segment.speaker}] " if segment.speaker else ""
        blocks.append(f"{position}\n{start} --> {end}\n{speaker_prefix}{text}\n")
    return "\n".join(blocks)


def to_docx(segments: Sequence[TranscriptLike], title: str = "Transcript") -> bytes:
    """Word document with a heading and one paragraph per segment."""
    document = Document()
    document.add_heading(title, level=1)
    for segment in segments:
        timecode = format_srt_timestamp(segment.start)[:-4]  # HH:MM:SS
        prefix = f"[{segment.speaker}] " if segment.speaker else ""
        document.add_paragraph(f"{timecode}  {prefix}{segment.text}")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
