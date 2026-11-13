"""Transcription engines.

`FasterWhisperTranscriber` wraps faster-whisper with a lazily-loaded
process-wide singleton model (the weights are heavy; load them once).
`FakeTranscriber` produces deterministic segments so tests and CI can
exercise the whole pipeline without downloading model weights.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from sokhan.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class Segment:
    """One transcript span with chunk-local timestamps (seconds)."""

    start: float
    end: float
    text: str
    avg_logprob: float = 0.0
    speaker: str | None = None


class Transcriber(Protocol):
    def transcribe(
        self, samples: np.ndarray, sample_rate: int, language: str
    ) -> list[Segment]: ...


class FasterWhisperTranscriber:
    """Chunk-local transcription with faster-whisper."""

    def __init__(
        self,
        model_size: str | None = None,
        device: str | None = None,
        compute_type: str | None = None,
    ) -> None:
        settings = get_settings()
        self.model_size = model_size or settings.whisper_model_size
        self.device = device or settings.whisper_device
        self.compute_type = compute_type or settings.whisper_compute_type
        self._model = None

    def _load(self):  # type: ignore[no-untyped-def]
        if self._model is None:
            from faster_whisper import WhisperModel

            logger.info(
                "loading whisper model %s (%s/%s)",
                self.model_size,
                self.device,
                self.compute_type,
            )
            self._model = WhisperModel(
                self.model_size, device=self.device, compute_type=self.compute_type
            )
        return self._model

    def transcribe(
        self, samples: np.ndarray, sample_rate: int, language: str
    ) -> list[Segment]:
        model = self._load()
        options: dict[str, object] = {"vad_filter": True}
        if language and language != "auto":
            options["language"] = language
        segments_iter, _info = model.transcribe(samples, **options)  # type: ignore[arg-type]
        segments: list[Segment] = []
        for segment in segments_iter:
            text = segment.text.strip()
            if not text:
                continue
            segments.append(
                Segment(
                    start=float(segment.start),
                    end=float(segment.end),
                    text=text,
                    avg_logprob=float(segment.avg_logprob),
                )
            )
        return segments


class FakeTranscriber:
    """Deterministic engine for tests: one or two fixed Persian segments."""

    def transcribe(
        self, samples: np.ndarray, sample_rate: int, language: str
    ) -> list[Segment]:
        duration = len(samples) / sample_rate
        segments: list[Segment] = []
        if duration >= 1.0:
            segments.append(
                Segment(start=0.0, end=min(2.0, duration / 2), text="سلام بر تو", avg_logprob=-0.2)
            )
        if duration >= 3.0:
            segments.append(
                Segment(
                    start=min(2.5, duration - 1.0),
                    end=duration,
                    text="حالت چطور است",
                    avg_logprob=-0.3,
                )
            )
        return segments


_transcriber: Transcriber | None = None


def get_transcriber() -> Transcriber:
    """Process-wide singleton; the model is heavy and loaded once."""
    global _transcriber
    if _transcriber is None:
        _transcriber = FasterWhisperTranscriber()
    return _transcriber


def set_transcriber(transcriber: Transcriber | None) -> None:
    """Swap the singleton; used by tests to inject the fake engine."""
    global _transcriber
    _transcriber = transcriber
