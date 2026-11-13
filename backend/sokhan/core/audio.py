"""Audio decoding and storage helpers built on PyAV.

faster-whisper ships PyAV, so decoding needs no external ffmpeg install.
Everything is normalized to mono float32 PCM at 16 kHz before chunking.
"""

import re
from pathlib import Path

import av
import numpy as np
from faster_whisper.audio import decode_audio

from sokhan.config import get_settings

SAMPLE_RATE = 16000

ALLOWED_EXTENSIONS = {".mp3", ".m4a", ".mp4", ".wav", ".ogg", ".opus", ".webm", ".flac"}

_SAFE_SUFFIX = re.compile(r"^[a-z0-9]{1,8}$")


def decode_to_mono_16k(path: str | Path) -> np.ndarray:
    """Decode any media file to mono float32 PCM at 16 kHz."""
    return decode_audio(str(path), sampling_rate=SAMPLE_RATE)


def probe_duration_seconds(path: str | Path) -> float:
    """Return the audio duration in seconds without decoding everything.

    Uses container metadata when available and falls back to a full decode
    (needed for raw WAV files that carry no container duration).
    """
    try:
        with av.open(str(path)) as container:
            if container.duration and container.duration > 0:
                # container.duration is in AV_TIME_BASE units (microseconds)
                return container.duration / 1_000_000
            for stream in container.streams:
                if stream.duration is not None and stream.time_base is not None:
                    return float(stream.duration * stream.time_base)
    except av.AVError:
        pass
    return float(len(decode_to_mono_16k(path)) / SAMPLE_RATE)


def audio_dir() -> Path:
    directory = Path(get_settings().data_dir) / "audio"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def save_upload(data: bytes, job_id: str, original_filename: str) -> Path:
    """Persist an upload under DATA_DIR/audio with a safe extension."""
    suffix = Path(original_filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS or not _SAFE_SUFFIX.match(suffix[1:]):
        suffix = ".bin"
    path = audio_dir() / f"{job_id}{suffix}"
    path.write_bytes(data)
    return path


def delete_audio(path: str | Path) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:  # pragma: no cover - best effort cleanup
        pass
