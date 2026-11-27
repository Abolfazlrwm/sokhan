---
title: Sokhan سخن
emoji: "\U0001F3A4"
colorFrom: indigo
colorTo: purple
sdk: static
pinned: false
license: other
license_name: PolyForm Noncommercial 1.0.0
license_link: https://github.com/Abolfazlrwm/sokhan/blob/main/LICENSE
short_description: تبدیل گفتار فارسی به نوشتار — اجرا کامل درون مرورگر
---

# Sokhan — Persian speech-to-text, in your browser

A live demo of [Sokhan](https://github.com/Abolfazlrwm/sokhan)'s speech
engine that runs **entirely client-side**: Whisper (ONNX) executes on
the visitor's own machine via
[transformers.js](https://huggingface.co/docs/transformers.js) — nothing
is uploaded, no backend, no compute cost. Persian RTL UI, mic recording,
file upload and a bundled benchmark sample clip.

Speed and reliability: the demo picks the fastest backend the browser
offers — WebGPU (fp32 encoder + q4 decoder) on Chrome/Edge, WASM q8
everywhere else — and owns the 30 s/5 s windowing itself, so it reports
per-window progress with an ETA, shows an elapsed timer, enforces a
duration cap (30 min on WebGPU, 10 min on WASM) and offers a real cancel
button that terminates the worker. Audio is decoded at the context's
natural rate and resampled offline to 16 kHz, avoiding a Chromium hang
on opus/webm inputs.

Three models are selectable: untuned **base** and **small** so anyone can
hear the difference, plus an opt-in **large-v3-turbo**
([`onnx-community/whisper-large-v3-turbo`](https://huggingface.co/onnx-community/whisper-large-v3-turbo),
fp16 encoder + q4 decoder, ~1.5 GB download) that runs only on WebGPU and
measured WER 43.8% on the Persian fixture — the same engine the
self-hosted backend runs by default. The **fine-tuned** checkpoint
([`Abol0pati/whisper-small-fa-sokhan`](https://huggingface.co/Abol0pati/whisper-small-fa-sokhan),
LoRA on 500 Common Voice fa clips, measured WER 79.3% vs 80.5% baseline)
is served by the same engine Sokhan runs in production — the app for that
lives in [`space/gradio/`](https://github.com/Abolfazlrwm/sokhan/tree/main/space/gradio)
for self-hosting, because HF's 2026 pricing gates hosted Gradio/Docker
Spaces behind a PRO subscription and only **static** Spaces (like this
page) remain free. Porting the fine-tune to ONNX for the browser is on
the roadmap ([docs/ROADMAP.md](https://github.com/Abolfazlrwm/sokhan/blob/main/docs/ROADMAP.md)).

Persian Common Voice is colloquial and noisy — expect real mistakes, from
every Whisper size.
