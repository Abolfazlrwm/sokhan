---
language:
  - fa
license: cc0-1.0
base_model: openai/whisper-tiny
library_name: ctranslate2
tags:
  - whisper
  - persian
  - asr
  - sokhan
  - lora
datasets:
  - pymmdrza/Common-Voice-Speech-26.0-Persian-Clean
metrics:
  - wer
  - cer
model-index:
  - name: whisper-tiny-fa-sokhan
    results:
      - task:
          type: automatic-speech-recognition
          name: Automatic Speech Recognition
        dataset:
          name: Common Voice fa — Sokhan 12-clip fixture (CC-0)
          type: mozilla-foundation/common_voice_17_0
        metrics:
          - type: wer
            value: 0.95
            name: WER (fixture, CPU int8, v3 decode stack)
          - type: cer
            value: 0.388
            name: CER (fixture, CPU int8, v3 decode stack)
---

# whisper-tiny-fa-sokhan

A LoRA fine-tune of `openai/whisper-tiny` on Persian speech, converted to
CTranslate2 (`int8`) so it can be served directly by
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) — the engine
[Sokhan](https://github.com/Abolfazlrwm/sokhan) ships.

**Honest summary: this model does NOT beat the untuned baseline.** It exists
as the reproducible artifact of the project's first real fine-tune run,
executed on CPU (2 cores, no GPU) on 2026-11-15. See the measured numbers
below and the notebook + scripts in the Sokhan repo to reproduce or to do
better on a real GPU. For a Persian fine-tune that DOES beat its weight
class, see [`whisper-small-fa-sokhan`](https://huggingface.co/Abol0pati/whisper-small-fa-sokhan)
(66.2% WER vs 70.0% untuned small under the same stack).

## Training data

- Source: `pymmdrza/Common-Voice-Speech-26.0-Persian-Clean` (CC-0,
  cv-corpus-26.0), **train split only** — the Sokhan benchmark fixture lives
  in the test split and was never trained on.
- 518 clips, 45.0 minutes of validated Persian speech.

## Training setup

- LoRA rank 16 on `q_proj`/`v_proj`, 294,912 trainable params (0.78% of the
  base model), learning rate 1e-4, batch size 2, 2 epochs (508 optimizer
  steps), fp32 on CPU.
- Training loss fell 3.84 -> 1.55; held-out eval loss 1.646 -> 1.545; held-out
  WER (10 clips, product normalization) stayed flat at 94.6% across epochs.

## Measured results

12-clip Common Voice (fa) fixture from the Sokhan repo
(`benchmarks/benchmark_wer.py --models Abol0pati/whisper-tiny-fa-sokhan`),
CPU int8, faster-whisper 1.2.1 / CTranslate2 4.9.1. The **v3 decode stack**
(2026-11-27) is what the product ships: beam_size=5, the VAD filter on, no
initial prompt, and the language-drift guard; per-clip session archived at
`benchmarks/results/archive/20261127-141843-Abol0pati_whisper-tiny-fa-sokhan.json`.

| model | WER (v1 harness, 11-15) | WER (v3 stack, 11-27) | CER (v3 stack) |
| --- | --- | --- | --- |
| whisper-tiny (baseline) | 93.9% | 93.8% | 42.7% |
| **this model** | 103.7% | **95.0%** | **38.8%** |

The v3 stack's VAD + drift guard narrow most of the v1 gap (103.7% -> 95.0%)
and cut character errors by 3.9 points (38.8% vs 42.7%) — but the LoRA still
does not beat untuned `tiny` on word error rate, and the whole tiny class
sits far below `small` (70.0%) and `large-v3-turbo` (37.5%) on the same
fixture. Conclusion stands: at tiny scale (45 minutes of data, 2 epochs) LoRA
does not improve Persian WER. Meaningful gains need the documented free-GPU
path: `whisper-small` (or larger) trained on hours of data in
[Google Colab / Kaggle](https://github.com/Abolfazlrwm/sokhan/blob/main/docs/free-gpu.md)
via `training/finetune_fa_colab.ipynb`.

## Usage

```python
from faster_whisper import WhisperModel

model = WhisperModel("Abol0pati/whisper-tiny-fa-sokhan", device="cpu", compute_type="int8")
segments, info = model.transcribe("audio.wav", language="fa", beam_size=5)
```

## License

- Base model weights: OpenAI Whisper, MIT.
- Fine-tuning data: Mozilla Common Voice (fa), CC-0 1.0.
- This repo: MIT.
