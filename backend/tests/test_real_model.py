"""End-to-end check against the real Whisper model.

Skipped unless SOKHAN_REAL_MODEL_TEST=1. Requires espeak-ng for the synthetic
Persian sample and network access for the model weights. This test never runs
in CI; it exists so a developer can validate a real model locally before a
release.
"""

import os
import subprocess

import pytest

pytestmark = pytest.mark.gpu_optional

SAMPLE_TEXT = "سلام، این یک آزمایش است."


def test_real_whisper_transcribes_synthetic_persian(tmp_path):
    if os.environ.get("SOKHAN_REAL_MODEL_TEST") != "1":
        pytest.skip("set SOKHAN_REAL_MODEL_TEST=1 to run the real Whisper model")

    wav_path = tmp_path / "sample.wav"
    subprocess.run(
        ["espeak-ng", "-v", "fa", "-w", str(wav_path), SAMPLE_TEXT],
        check=True,
        capture_output=True,
    )

    from sokhan.core.audio import decode_to_mono_16k
    from sokhan.core.transcribe import FasterWhisperTranscriber

    engine = FasterWhisperTranscriber(model_size="small", device="cpu", compute_type="int8")
    segments = engine.transcribe(decode_to_mono_16k(wav_path), 16000, "fa")

    assert segments, "engine returned no segments"
    for segment in segments:
        assert 0 <= segment.start <= segment.end
    joined = " ".join(segment.text for segment in segments)
    assert "سلام" in joined
