"""No-op diarizer used until a real speaker model ships."""

import numpy as np

from sokhan.diarization.base import SpeakerTurn


class StubDiarizer:
    """Returns no speaker turns; pipeline segments keep speaker=None."""

    name = "stub"

    def diarize(self, samples: np.ndarray, sample_rate: int) -> list[SpeakerTurn]:
        return []


def get_diarizer() -> StubDiarizer:
    return StubDiarizer()
