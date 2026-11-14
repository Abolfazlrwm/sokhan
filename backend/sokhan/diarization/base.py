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

    def diarize(self, samples: np.ndarray, sample_rate: int) -> list[SpeakerTurn]: ...
