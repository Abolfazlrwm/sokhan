"""Transcription engines.

`FasterWhisperTranscriber` wraps faster-whisper with a lazily-loaded
process-wide singleton model (the weights are heavy; load them once).
`FakeTranscriber` produces deterministic segments so tests and CI can
exercise the whole pipeline without downloading model weights.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from sokhan.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class Segment:
    """One transcript span with chunk-local timestamps (seconds).

    `confidence` is exp(avg_logprob) in (0, 1] — the model's own probability
    estimate for the span. `None` when the engine does not produce one.
    """

    start: float
    end: float
    text: str
    avg_logprob: float = 0.0
    confidence: float | None = None
    speaker: str | None = None


# Called with the fraction (0..1) of the current chunk decoded so far.
ProgressCallback = Callable[[float], None]


class Transcriber(Protocol):
    def transcribe(
        self, samples: np.ndarray, sample_rate: int, language: str
    ) -> list[Segment]: ...


def reports_progress(engine: object) -> bool:
    """Whether `engine.transcribe` accepts an `on_progress` callback.

    Opt-in via a class attribute, so third-party engines and test doubles
    with the plain three-argument signature keep working unchanged.
    """
    return bool(getattr(engine, "reports_progress", False))


class FasterWhisperTranscriber:
    """Chunk-local transcription with faster-whisper."""

    reports_progress = True

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
        self,
        samples: np.ndarray,
        sample_rate: int,
        language: str,
        on_progress: ProgressCallback | None = None,
    ) -> list[Segment]:
        model = self._load()
        settings = get_settings()
        options: dict[str, object] = {
            "vad_filter": True,
            "beam_size": settings.whisper_beam_size,
        }
        if settings.whisper_initial_prompt:
            options["initial_prompt"] = settings.whisper_initial_prompt
        if language and language != "auto":
            options["language"] = language
        segments_iter, _info = model.transcribe(samples, **options)  # type: ignore[arg-type]
        chunk_seconds = len(samples) / sample_rate
        segments: list[Segment] = []
        # faster-whisper decodes lazily, segment by segment, so each step of
        # this loop is real work done: report how far into the chunk it is.
        for segment in segments_iter:
            if on_progress is not None and chunk_seconds > 0:
                on_progress(min(1.0, float(segment.end) / chunk_seconds))
            text = segment.text.strip()
            if not text:
                continue
            avg_logprob = float(segment.avg_logprob)
            segments.append(
                Segment(
                    start=float(segment.start),
                    end=float(segment.end),
                    text=text,
                    avg_logprob=avg_logprob,
                    confidence=math.exp(avg_logprob),
                )
            )
        return segments


class FakeTranscriber:
    """Deterministic engine for tests: one or two fixed Persian segments."""

    reports_progress = True

    def transcribe(
        self,
        samples: np.ndarray,
        sample_rate: int,
        language: str,
        on_progress: ProgressCallback | None = None,
    ) -> list[Segment]:
        duration = len(samples) / sample_rate
        segments: list[Segment] = []
        if duration >= 1.0:
            segments.append(
                Segment(
                    start=0.0,
                    end=min(2.0, duration / 2),
                    text="سلام بر تو",
                    avg_logprob=-0.2,
                    confidence=0.819,
                )
            )
        if duration >= 3.0:
            segments.append(
                Segment(
                    start=min(2.5, duration - 1.0),
                    end=duration,
                    text="حالت چطور است",
                    avg_logprob=-0.3,
                    confidence=0.741,
                )
            )
        if on_progress is not None and duration > 0:
            for segment in segments:
                on_progress(min(1.0, segment.end / duration))
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
