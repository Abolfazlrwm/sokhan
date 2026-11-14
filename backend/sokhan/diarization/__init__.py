"""Speaker diarization interface and engine selection.

Sokhan ships the contract plus three engines behind ``DIARIZATION_ENGINE``:

- ``stub`` (default): no speaker labels, exactly the v1 behaviour
- ``energy``: a dependency-free heuristic two-cluster splitter
- ``pyannote``: a real neural pipeline, requires torch + pyannote.audio and
  a Hugging Face token for the gated weights; if anything is missing the
  factory falls back to the stub so transcription never breaks

See docs/adr/0003-diarization-interface.md and
docs/adr/0004-diarization-engines.md.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Protocol

from sokhan.config import get_settings
from sokhan.diarization.base import (
    Diarizer,
    DiarizerUnavailableError,
    SpeakerTurn,
)
from sokhan.diarization.energy import EnergyClusterDiarizer
from sokhan.diarization.stub import StubDiarizer

logger = logging.getLogger(__name__)

__all__ = [
    "Diarizer",
    "DiarizerUnavailableError",
    "EnergyClusterDiarizer",
    "SpeakerTurn",
    "StubDiarizer",
    "get_diarizer",
    "label_segments",
]


def get_diarizer(settings=None) -> Diarizer:
    """Build the configured diarizer; never raises for a missing engine."""
    settings = settings or get_settings()
    engine = str(getattr(settings, "diarization_engine", "stub")).strip().lower()

    if engine == "pyannote":
        try:
            import pyannote.audio  # noqa: F401 - availability probe

            from sokhan.diarization.pyannote import PyannoteDiarizer
        except Exception as exc:  # pragma: no cover - depends on extras
            logger.warning("pyannote not importable (%s); using stub", exc)
            return StubDiarizer()
        if not str(getattr(settings, "pyannote_hf_token", "")):
            logger.warning("pyannote selected but no HF token configured; using stub")
            return StubDiarizer()
        return PyannoteDiarizer(
            hf_token=str(settings.pyannote_hf_token),
            model_name=str(
                getattr(settings, "pyannote_model", "pyannote/speaker-diarization-3.1")
            ),
        )
    if engine == "energy":
        return EnergyClusterDiarizer()
    return StubDiarizer()


class SpeakerLabelable(Protocol):
    """Anything with segment timing fields and an assignable speaker."""

    start: float
    end: float
    speaker: str | None


def label_segments(
    segments: Sequence[SpeakerLabelable],
    turns: Sequence[SpeakerTurn],
    min_overlap_ratio: float = 0.2,
) -> None:
    """Assign ``segment.speaker`` in place by maximum temporal overlap.

    A segment inherits the label of the turn covering most of it, and only
    when that turn actually covers ``min_overlap_ratio`` of the segment —
    otherwise the segment keeps no speaker label.
    """
    for segment in segments:
        span = float(segment.end) - float(segment.start)
        best_speaker: str | None = None
        best_ratio = min_overlap_ratio
        for turn in turns:
            overlap = min(float(segment.end), turn.end) - max(
                float(segment.start), turn.start
            )
            if overlap <= 0 or span <= 0:
                continue
            ratio = overlap / span
            if ratio > best_ratio:
                best_speaker = turn.speaker
                best_ratio = ratio
        segment.speaker = best_speaker
