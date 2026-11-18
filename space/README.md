---
title: Sokhan سخن
emoji: "\U0001F3A4"
colorFrom: indigo
colorTo: purple
sdk: gradio
app_file: app.py
pinned: false
license: mit
short_description: تبدیل گفتار فارسی به نوشتار — مدل ریزتنظیم‌شده Whisper
---

# Sokhan — Persian speech-to-text demo

A live demo of [Sokhan](https://github.com/Abolfazlrwm/sokhan)'s speech
engine: faster-whisper on CPU (int8) serving a LoRA fine-tuned
`whisper-small` checkpoint trained on 500 Common Voice (fa) clips on a
free Colab T4 —
[`Abol0pati/whisper-small-fa-sokhan`](https://huggingface.co/Abol0pati/whisper-small-fa-sokhan).

The radio lets you A/B the same clip through the fine-tuned model and the
untuned `small` baseline. Measured on the project's fixed 12-clip fixture:
**WER 79.3%** (fine-tuned) vs **80.5%** (baseline) — a real but small
margin, honestly at the edge of noise on a fixture this size. Persian
Common Voice is colloquial and noisy; expect mistakes.

Self-hosting the full product (web dashboard, Telegram bot, API, archive):
see the repository README.
