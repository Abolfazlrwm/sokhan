"""Speaker diarization contract shared by every engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


class DiarizerUnavailableError(RuntimeError):
    """Raised when a selected engine cannot run in this environment."""


@dataclass(frozen=True)
class SpeakerTurn:
    start: float
    end: float
    speaker: str


class Diarizer(Protocol):
    name: str
    # Whether the engine needs the whole signal in one array. The pipeline
    # streams audio block-by-block when this is False, so engines that
    # could work incrementally (or produce nothing, like the stub) opt in
    # to the low-memory decode path by overriding it.
    requires_full_audio: bool

    def diarize(self, samples: np.ndarray, sample_rate: int) -> list[SpeakerTurn]: ...
