"""Neural speaker diarization via pyannote.audio (optional).

pyannote/speaker-diarization-3.1 is a gated Hugging Face model: the runtime
needs ``torch`` and ``pyannote.audio`` installed plus an access token that
the operator generated after accepting the model's usage terms. None of that
is bundled with Sokhan; when the engine is selected but the environment does
not provide it, the factory falls back to the stub so jobs keep running.
"""

from __future__ import annotations

import io
import logging
import tempfile
import wave
from pathlib import Path

import numpy as np

from sokhan.diarization.base import DiarizerUnavailableError, SpeakerTurn

logger = logging.getLogger(__name__)


class PyannoteDiarizer:
    """Runs the pyannote speaker-diarization pipeline on decoded audio."""

    name = "pyannote"

    def __init__(self, hf_token: str, model_name: str) -> None:
        self.hf_token = hf_token
        self.model_name = model_name
        self._pipeline = None

    def _load(self):  # type: ignore[no-untyped-def]
        if self._pipeline is None:
            try:
                from pyannote.audio import Pipeline
            except ImportError as exc:  # pragma: no cover - depends on extras
                raise DiarizerUnavailableError(
                    "pyannote.audio is not installed; install backend[diarize] to use it"
                ) from exc
            logger.info("loading pyannote pipeline %s", self.model_name)
            try:
                self._pipeline = Pipeline.from_pretrained(
                    self.model_name, token=self.hf_token or None
                )
            except TypeError:  # older releases expose use_auth_token
                self._pipeline = Pipeline.from_pretrained(
                    self.model_name, use_auth_token=self.hf_token or None
                )
        return self._pipeline

    def diarize(self, samples: np.ndarray, sample_rate: int) -> list[SpeakerTurn]:
        if not self.hf_token:
            raise DiarizerUnavailableError("pyannote selected but no HF token configured")
        pipeline = self._load()
        pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(sample_rate)
            handle.writeframes(pcm.tobytes())
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp:
            temp.write(buffer.getvalue())
            temp_path = Path(temp.name)
        try:
            annotation = pipeline(str(temp_path))
        finally:
            temp_path.unlink(missing_ok=True)

        turns: list[SpeakerTurn] = []
        for turn, _meta, label in annotation.itertracks(yield_label=True):
            turns.append(SpeakerTurn(float(turn.start), float(turn.end), str(label)))
        return turns
