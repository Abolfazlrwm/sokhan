"""Speaker diarization interface.

Sokhan ships only the contract for now: real diarization (pyannote) requires
gated Hugging Face weights and a much bigger runtime, so v1 keeps it behind
this interface and a no-op stub. See docs/adr/0003-diarization-interface.md.
"""

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class SpeakerTurn:
    start: float
    end: float
    speaker: str


class Diarizer(Protocol):
    name: str

    def diarize(self, samples: np.ndarray, sample_rate: int) -> list[SpeakerTurn]: ...
