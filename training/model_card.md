---
language:
  - fa
license: other
license_name: PolyForm Noncommercial 1.0.0
license_link: https://github.com/Abolfazlrwm/sokhan/blob/main/LICENSE
base_model:
  - openai/whisper-small
tags:
  - asr
  - whisper
  - persian
  - lora
  - peft
  - faster-whisper
  - ctranslate2
datasets:
  - mozilla-foundation/common_voice_17_0
metrics:
  - wer
  - cer
model-index:
  - name: whisper-small-fa-sokhan
    results:
      - task:
          type: automatic-speech-recognition
          name: Automatic Speech Recognition
        dataset:
          name: Common Voice fa — Sokhan 12-clip fixture (CC-0)
          type: mozilla-foundation/common_voice_17_0
        metrics:
          - type: wer
            value: 0.793
            name: WER (fixture, CPU int8)
          - type: cer
            value: 0.249
            name: CER (fixture, CPU int8)
---

# whisper-small-fa-sokhan

A Persian-adapted `whisper-small`: LoRA fine-tune (r=16, alpha=32,
dropout=0.05 on `q_proj`/`v_proj`, lr 1e-4, 3 epochs) on **500 Common
Voice (fa) clips (~45 minutes of speech)**, trained in ~7 minutes on a
free Colab T4, then merged and converted to CTranslate2 so
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) can serve it
on CPU int8 — the same config the
[Sokhan](https://github.com/Abolfazlrwm/sokhan) product uses in production.

## Measured results

Every number below comes from a reproducible run
(`benchmarks/benchmark_wer.py`): 12 real Common Voice (fa) clips with
human-verified references, beam_size=5, the same Persian normalization
applied to reference and hypothesis. Sessions 2026-11-18 (v1/v2 harness,
faster-whisper 1.2.1 / CTranslate2 4.9.0) and 2026-11-27 (v3 stack,
CTranslate2 4.9.1), CPU int8.

| model | WER (v1 harness) | WER (v2 harness) | WER (v3 stack: VAD + drift guard, no prompt) |
| --- | --- | --- | --- |
| openai whisper-small (baseline) | 80.5% | 75.0% | 70.0% |
| **whisper-small-fa-sokhan** | **79.3%** | **75.0%** | **66.2%** |
| openai whisper-medium (untuned, for scale) | — | 56.2% | 48.8% |

The v3 column (per-clip session archived at
`benchmarks/results/archive/20261127-131850-Abol0pati_whisper-small-fa-sokhan.json`)
flips the earlier tie: under the stack the product actually ships, this
checkpoint runs **3.8 WER points ahead of the untuned baseline** —
the stack's VAD + drift-guard improvements compound on the fine-tuned
weights.

In-training held-out eval (10 clips): WER 85.1% → 81.6%; training loss
3.63 → 1.75. With a Persian orthography initial prompt alone (no polish),
this checkpoint measures 72.0% vs 76.8% without — the prompt is worth
−4.8 WER points on this model, more than the LoRA itself contributed.

**Honest caveats.** A 12-clip fixture puts the small margins near the
noise floor; the direction matches the in-training eval but the ceiling
is unknown until the same notebook runs over the full ~10-hour manifest
(`MAX_SAMPLES=0`, ~2 h on a free T4) — and the measured untuned
small-vs-medium gap (70.0% vs 48.8% under v3) says the next fine-tune
should target `whisper-medium`, not more data on `small`. Common Voice fa is
colloquial and noisy — these WER numbers are much higher than typical
read-speech benchmarks. Do not cite this model as production-ready
Persian ASR yet.

## Usage

```python
from faster_whisper import WhisperModel

model = WhisperModel("Abol0pati/whisper-small-fa-sokhan",
                     device="cpu", compute_type="int8")
segments, info = model.transcribe("audio.wav", language="fa", beam_size=5)
print(" ".join(s.text.strip() for s in segments))
```

A free in-browser demo runs at
[hf.co/spaces/Abol0pati/sokhan-fa-demo](https://huggingface.co/spaces/Abol0pati/sokhan-fa-demo)
— Whisper executes entirely client-side there (transformers.js, ONNX q8,
nothing uploaded), with the untuned base/small checkpoints selectable.
Serving **this fine-tuned checkpoint** needs a real engine: the Gradio app
in [`space/gradio/`](https://github.com/Abolfazlrwm/sokhan/tree/main/space/gradio)
runs it with the same faster-whisper config as production, self-hosted or
on a PRO Space (HF gates hosted Gradio Spaces behind PRO since 2026).

## Training & reproduction

- Pipeline and one-click Colab notebook:
  [`training/`](https://github.com/Abolfazlrwm/sokhan/tree/main/training) +
  [docs/free-gpu.md](https://github.com/Abolfazlrwm/sokhan/blob/main/docs/free-gpu.md)
- Data: public CC-0 Common Voice (fa) mirror, `train` split, 500 clips /
  ~45 min speech
- Method: parameter-efficient LoRA (PEFT) on whisper-small, adapter only —
  base weights untouched, merged after training, then converted with
  `ct2-transformers-converter --quantization float16` (serving quantizes
  to int8)

Persian Common Voice files are no longer re-published as downloads by
Mozilla; the pipeline uses the public parquet mirror instead. Licensing
follows CC-0 for the data, and the PolyForm Noncommercial 1.0.0
source-available license for the code and the fine-tuned weights — free
for noncommercial use, commercial use requires a license from the author
(https://github.com/Abolfazlrwm). The base Whisper weights remain MIT
(OpenAI).
