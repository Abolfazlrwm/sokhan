"""Sokhan live demo — Persian speech-to-text in the browser.

Runs the exact engine Sokhan serves in production (faster-whisper on CPU,
int8) over the LoRA fine-tuned Whisper checkpoint published on the Hub.

Designed to be deployed as a Hugging Face Space (sdk: gradio), but it is a
plain Gradio app: `python app.py` runs it locally too. The A/B radio lets
anyone transcribe the same clip through the fine-tuned model and the
untuned baseline, which is the honest way to hear what 500 fine-tune clips
change.

Numbers first: the fine-tuned checkpoint measures WER 79.3% vs 80.5% for
the baseline on the 12-clip Common Voice (fa) fixture
(benchmarks/README.md). Persian Common Voice is colloquial and noisy, so
both models make plenty of mistakes — this demo exists so people can try
the engine without self-hosting anything.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import gradio as gr
from faster_whisper import WhisperModel

# The fine-tuned checkpoint to showcase; override for forked Spaces.
SOKHAN_MODEL_ID = os.environ.get("SOKHAN_MODEL_ID", "Abol0pati/whisper-small-fa-sokhan")
BASELINE_MODEL_ID = os.environ.get("BASELINE_MODEL_ID", "small")

MODELS: dict[str, WhisperModel] = {}

# Display label -> internal key. Plain strings keep this app portable
# across Gradio versions (no (value, label) tuple magic).
CHOICE_LABELS = {
    "finetuned": "مدل ریزتنظیم‌شده (Sokhan)",
    "baseline": "مدل پایه (whisper-small)",
}
MODEL_IDS = {
    "finetuned": SOKHAN_MODEL_ID,
    "baseline": BASELINE_MODEL_ID,
}
LABEL_TO_KEY = {label: key for key, label in CHOICE_LABELS.items()}


def get_model(key: str) -> WhisperModel:
    """Lazily build one WhisperModel per choice; reused across requests."""
    if key not in MODELS:
        MODELS[key] = WhisperModel(MODEL_IDS[key], device="cpu", compute_type="int8")
    return MODELS[key]


def transcribe(audio_path: str | None, label: str) -> tuple[str, str]:
    """Transcribe one clip; returns (transcript, stats line)."""
    if not audio_path or not Path(audio_path).exists():
        return "", "یک فایل صوتی انتخاب یا ضبط کنید."

    audio_path = str(Path(audio_path))
    model = get_model(LABEL_TO_KEY.get(label, "finetuned"))

    start = time.perf_counter()
    segments, info = model.transcribe(audio_path, language="fa", beam_size=5)
    parts: list[str] = []
    for segment in segments:
        parts.append(segment.text.strip())
    elapsed = time.perf_counter() - start

    transcript = " ".join(parts).strip()
    if not transcript:
        transcript = "(متنی تشخیص داده نشد — شاید صدا بیش‌ازحد کوتاه یا نویزی بود.)"

    audio_s = info.duration
    rtf = elapsed / audio_s if audio_s else 0.0
    stats = (
        f"مدت صدا: {audio_s:.1f} ثانیه | زمان پردازش: {elapsed:.1f} ثانیه "
        f"(≈ {rtf:.1f} برابرِ زمان واقعی، CPU int8)"
    )
    return transcript, stats


TITLE = "سخن · تبدیل گفتار فارسی به نوشتار"
DESCRIPTION = """
دموی زنده‌ی موتور **Sokhan** — همان موتور faster-whisper که در خودِ محصول
روی CPU سرو می‌شود، اینجا با چک‌پوینت ریزتنظیم‌شده با LoRA روی ۵۰۰ کلیپ
Common Voice فارسی (آموزش رایگان روی T4 کولب).

مدل ریزتنظیم‌شده در اندازه‌گیری ثابت پروژه به **WER 79.3%** رسیده
(پایه: 80.5%) — اما داده‌ی آموزش کم است و Common Voice فارسی محاوره‌ای و
پرنویز است؛ هر دو مدل اشتباه می‌کنند. برای مقایسه، همان صدا را با هر دو
مدل اجرا کنید.
کد کامل: [github.com/Abolfazlrwm/sokhan](https://github.com/Abolfazlrwm/sokhan)
"""

CSS = """
.gradio-container {direction: rtl; text-align: right;}
.transcript textarea {font-size: 1.05rem; line-height: 1.9;}
"""

# Gradio 6.0 moved the css parameter from Blocks() to launch(); support both
# so the Space builds on whatever SDK version HF ships.
GRADIO_MAJOR = int(gr.__version__.split(".")[0])
BLOCKS_CSS = {"css": CSS} if GRADIO_MAJOR < 6 else {}
LAUNCH_KWARGS = {"css": CSS} if GRADIO_MAJOR >= 6 else {}

with gr.Blocks(title=TITLE, **BLOCKS_CSS) as demo:
    gr.Markdown(f"# {TITLE}")
    gr.Markdown(DESCRIPTION)

    with gr.Row():
        audio_in = gr.Audio(
            sources=["microphone", "upload"],
            type="filepath",
            label="صدا — ضبط با میکروفن یا انتخاب فایل",
        )
        model_choice = gr.Radio(
            choices=list(CHOICE_LABELS.values()),
            value=CHOICE_LABELS["finetuned"],
            label="کدام مدل؟",
        )

    transcribe_btn = gr.Button("پیاده‌سازی", variant="primary")

    transcript_out = gr.Textbox(
        label="متن پیاده‌شده",
        lines=6,
        rtl=True,
        elem_classes=["transcript"],
        placeholder="بعد از پردازش اینجا نوشته می‌شود…",
    )
    stats_out = gr.Markdown("(نخستین اجرا مدل را دانلود می‌کند — چند دقیقه صبر کنید.)")

    transcribe_btn.click(
        fn=transcribe,
        inputs=[audio_in, model_choice],
        outputs=[transcript_out, stats_out],
    )

if __name__ == "__main__":
    demo.launch(**LAUNCH_KWARGS)
