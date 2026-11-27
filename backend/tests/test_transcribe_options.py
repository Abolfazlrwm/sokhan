"""The engine passes its decoding knobs through to faster-whisper."""

import numpy as np
from sokhan.core.transcribe import FasterWhisperTranscriber


class _CaptureModel:
    """Records the transcribe() kwargs instead of decoding anything."""

    def __init__(self) -> None:
        self.kwargs: dict | None = None

    def transcribe(self, audio, **kwargs):  # noqa: ANN001, ANN003
        self.kwargs = kwargs
        return iter([]), None


def _captured_kwargs(monkeypatch, env: dict[str, str], language: str) -> dict:
    from sokhan.config import get_settings

    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    try:
        transcriber = FasterWhisperTranscriber()
        model = _CaptureModel()
        transcriber._model = model  # skip the heavy lazy loader
        transcriber.transcribe(np.zeros(1600, dtype=np.float32), 16000, language)
        assert model.kwargs is not None
        return model.kwargs
    finally:
        get_settings.cache_clear()


def test_beam_size_and_initial_prompt_are_forwarded(monkeypatch):
    kwargs = _captured_kwargs(
        monkeypatch,
        {"WHISPER_BEAM_SIZE": "3", "WHISPER_INITIAL_PROMPT": "واژگان فنی پروژه"},
        language="fa",
    )
    assert kwargs["beam_size"] == 3
    assert kwargs["initial_prompt"] == "واژگان فنی پروژه"
    assert kwargs["vad_filter"] is True
    assert kwargs["language"] == "fa"


def test_default_beam_size_is_five_and_empty_prompt_is_omitted(monkeypatch):
    kwargs = _captured_kwargs(monkeypatch, {"WHISPER_INITIAL_PROMPT": ""}, language="fa")
    assert kwargs["beam_size"] == 5
    assert "initial_prompt" not in kwargs


def test_hotwords_are_forwarded_and_empty_is_omitted(monkeypatch):
    kwargs = _captured_kwargs(
        monkeypatch,
        {"WHISPER_HOTWORDS": "سخن، پیرانشهر، استادیوم آزادی"},
        language="fa",
    )
    assert kwargs["hotwords"] == "سخن، پیرانشهر، استادیوم آزادی"

    kwargs = _captured_kwargs(monkeypatch, {"WHISPER_HOTWORDS": ""}, language="fa")
    assert "hotwords" not in kwargs


def test_auto_language_skips_the_hint(monkeypatch):
    kwargs = _captured_kwargs(monkeypatch, {}, language="auto")
    assert "language" not in kwargs
