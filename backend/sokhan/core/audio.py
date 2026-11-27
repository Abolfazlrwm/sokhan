"""Audio decoding and storage helpers built on PyAV.

faster-whisper ships PyAV, so decoding needs no external ffmpeg install.
Everything is normalized to mono float32 PCM at 16 kHz before chunking.
Two decode modes share the same normalization: `decode_to_mono_16k` returns
the whole file in one array (legacy, and required by the diarizers), while
`iter_mono_16k_blocks` streams block by block so peak memory stays
proportional to the block size instead of the file length.
"""

import re
from collections.abc import Iterator
from pathlib import Path

import av
import numpy as np
from faster_whisper.audio import decode_audio

from sokhan.config import get_settings

SAMPLE_RATE = 16000

ALLOWED_EXTENSIONS = {".mp3", ".m4a", ".mp4", ".wav", ".ogg", ".opus", ".webm", ".flac"}

_SAFE_SUFFIX = re.compile(r"^[a-z0-9]{1,8}$")


class StorageUnavailableError(Exception):
    """DATA_DIR cannot be written, e.g. a root-owned volume or a full disk.

    It is a server fault, not a bad upload, so the API answers 503 and the
    real OSError stays in the server log instead of reaching the client.
    """


def decode_to_mono_16k(path: str | Path) -> np.ndarray:
    """Decode any media file to mono float32 PCM at 16 kHz."""
    return decode_audio(str(path), sampling_rate=SAMPLE_RATE)


def iter_mono_16k_blocks(
    path: str | Path, block_seconds: float = 30.0
) -> Iterator[np.ndarray]:
    """Stream-decode any media file to mono float32 PCM at 16 kHz.

    Yields blocks of roughly `block_seconds` (the final block may be
    shorter). Peak memory is one decoded frame plus one block, not the
    whole file — this is what makes multi-hour recordings transcribable on
    modest RAM. The samples are bit-compatible with `decode_to_mono_16k`:
    concatenating every block reproduces the full-decode array exactly.
    """
    if block_seconds <= 0:
        raise ValueError("block_seconds must be positive")
    block_samples = max(1, int(round(block_seconds * SAMPLE_RATE)))

    resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
    pending = np.zeros(0, dtype=np.float32)
    with av.open(str(path), mode="r", metadata_errors="ignore") as container:
        frames = container.decode(audio=0)
        for frame in frames:
            for resampled in resampler.resample(frame):
                # Same conversion faster-whisper applies after its s16
                # resampling: int16 samples scaled back into [-1, 1].
                chunk = (
                    resampled.to_ndarray().reshape(-1).astype(np.float32) / 32768.0
                )
                pending = np.concatenate([pending, chunk])
                while pending.size >= block_samples:
                    yield pending[:block_samples]
                    pending = pending[block_samples:].copy()
        # Drain the resampler's internal latency so the concatenated blocks
        # carry every sample the full decode returns.
        for resampled in resampler.resample(None):
            chunk = resampled.to_ndarray().reshape(-1).astype(np.float32) / 32768.0
            pending = np.concatenate([pending, chunk])
    if pending.size:
        yield pending


def probe_duration_seconds(path: str | Path, allow_full_decode: bool = True) -> float | None:
    """Return the audio duration in seconds without decoding everything.

    Uses container metadata when available and falls back to a full decode
    (needed for raw WAV files that carry no container duration). With
    `allow_full_decode=False` the fallback is skipped and `None` is
    returned instead — the streaming pipeline uses that form for its
    progress estimate, since a full decode there would defeat the point.
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
        if not allow_full_decode:
            return None
        raise
    if not allow_full_decode:
        return None
    return float(len(decode_to_mono_16k(path)) / SAMPLE_RATE)


def audio_dir() -> Path:
    directory = Path(get_settings().data_dir) / "audio"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def save_upload(data: bytes, job_id: str, original_filename: str) -> Path:
    """Persist an upload under DATA_DIR/audio with a safe extension.

    Raises StorageUnavailableError when the directory or file cannot be
    written; a partially written file is removed first.
    """
    suffix = Path(original_filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS or not _SAFE_SUFFIX.match(suffix[1:]):
        suffix = ".bin"
    try:
        path = audio_dir() / f"{job_id}{suffix}"
    except OSError as exc:
        raise StorageUnavailableError(str(exc)) from exc
    try:
        path.write_bytes(data)
    except OSError as exc:
        delete_audio(path)
        raise StorageUnavailableError(str(exc)) from exc
    return path


def delete_audio(path: str | Path) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:  # pragma: no cover - best effort cleanup
        pass
