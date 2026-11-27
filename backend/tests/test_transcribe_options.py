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


def test_vad_filter_defaults_on_and_can_be_disabled(monkeypatch):
    kwargs = _captured_kwargs(monkeypatch, {}, language="fa")
    assert kwargs["vad_filter"] is True

    kwargs = _captured_kwargs(monkeypatch, {"WHISPER_VAD_FILTER": "false"}, language="fa")
    assert kwargs["vad_filter"] is False


def test_drift_guard_does_not_fire_on_clean_decode(monkeypatch):
    """A Persian decode goes through exactly one model call."""
    from sokhan.config import get_settings
    from sokhan.core.transcribe import FasterWhisperTranscriber

    class _PersianModel:
        calls = 0

        def transcribe(self, audio, **kwargs):
            _PersianModel.calls += 1
            seg = type("S", (), {"text": "سلام بر تو همه", "start": 0.0, "end": 1.0,
                                 "avg_logprob": -0.2})()
            return iter([seg]), None

    get_settings.cache_clear()
    try:
        transcriber = FasterWhisperTranscriber()
        transcriber._model = _PersianModel()
        segments = transcriber.transcribe(np.zeros(16000, dtype=np.float32), 16000, "fa")
        assert [s.text for s in segments] == ["سلام بر تو همه"]
        assert _PersianModel.calls == 1
    finally:
        get_settings.cache_clear()


def test_drift_guard_retries_and_keeps_the_persian_retry(monkeypatch):
    """A Latin-script decode under a forced fa hint triggers one retry."""
    import logging

    from sokhan.core.transcribe import FasterWhisperTranscriber

    class _DriftModel:
        """First call decodes Icelandic, the deterministic retry is Persian."""

        def __init__(self) -> None:
            self.calls: list[dict] = []

        def transcribe(self, audio, **kwargs):
            self.calls.append(kwargs)
            if kwargs.get("temperature") == 0.0:
                text, logprob = "در هر حال اینکارو کردی", -0.3
            else:
                text, logprob = "Er hær hálf einhver kjærði?", -0.8
            seg = type("S", (), {"text": text, "start": 0.0, "end": 2.0,
                                 "avg_logprob": logprob})()
            return iter([seg]), None

    logging.disable(logging.WARNING)
    try:
        transcriber = FasterWhisperTranscriber()
        model = _DriftModel()
        transcriber._model = model
        segments = transcriber.transcribe(np.zeros(32000, dtype=np.float32), 16000, "fa")
        assert len(model.calls) == 2, "the guard must retry exactly once"
        assert model.calls[1]["temperature"] == 0.0
        assert model.calls[1]["vad_filter"] is True
        assert model.calls[1]["condition_on_previous_text"] is False
        assert [s.text for s in segments] == ["در هر حال اینکارو کردی"]
    finally:
        logging.disable(logging.NOTSET)


def test_language_guard_is_off_for_unlisted_languages():
    from sokhan.core.transcribe import looks_like_wrong_language

    # English has no script entry: even fully-Latin text never triggers a retry.
    assert looks_like_wrong_language("this is plain english text", "en") is False
    assert looks_like_wrong_language("این یک متن فارسی است", "fa") is False
    assert looks_like_wrong_language("Er hær hálf einhver kjærði?", "fa") is True
    # Too short to judge: no retry either way.
    assert looks_like_wrong_language("OK", "fa") is False
    assert looks_like_wrong_language("", "fa") is False


def test_script_ratio_measures_target_block_share():
    from sokhan.core.transcribe import script_ratio

    fa_blocks = ((0x0600, 0x06FF),)
    assert script_ratio("سلام دنیا", fa_blocks) == 1.0
    assert script_ratio("hello", fa_blocks) == 0.0
    assert 0.0 < script_ratio("سلام hello", fa_blocks) < 1.0
    assert script_ratio("123 !!!", fa_blocks) == 1.0  # no letters: not drift evidence
