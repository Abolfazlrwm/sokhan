"""No-op diarizer used when no speaker engine is configured."""

import numpy as np

from sokhan.diarization.base import SpeakerTurn


class StubDiarizer:
    """Returns no speaker turns; pipeline segments keep speaker=None."""

    name = "stub"

    def diarize(self, samples: np.ndarray, sample_rate: int) -> list[SpeakerTurn]:
        return []
