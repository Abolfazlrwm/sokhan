# Persian Whisper fine-tuning (month-two roadmap)

This directory is the start of the fine-tuning workstream: a complete,
runnable pipeline to adapt a Whisper checkpoint to Persian speech and convert
it back into the faster-whisper format Sokhan actually serves.

## What exists today

| file | purpose |
| --- | --- |
| `prepare_common_voice.py` | filters a Common Voice (fa) release into a training manifest (JSONL) |
| `train_whisper_lora.py` | LoRA fine-tune of a Whisper checkpoint with epoch-wise Persian WER evaluation |
| `requirements.txt` | the training-only dependency set |

## Why LoRA

Full fine-tuning of `whisper-small` (~244 M parameters) in fp32 needs memory
most self-hosters do not have. LoRA freezes the base weights and trains small
rank-decomposed adapters on the attention projections instead, which brings
the memory requirement down to a single consumer GPU (8–16 GB) while keeping
the model convertible back to a dense checkpoint.

## The loop, end to end

1. **Data.** Download a Common Voice Persian release (CC-0) and run the
   preparation script — it keeps clips with community consensus (two or more
   up-votes, no down-votes) and sane durations:

   ```bash
   python training/prepare_common_voice.py \
       --cv-root ~/datasets/cv-corpus-XX.X-YYYY-MM-DD/fa \
       --output training/data/cv-fa/manifest.jsonl \
       --max-hours 100
   ```

2. **Train.** LoRA adapters on `q_proj`/`v_proj` of `openai/whisper-small`:

   ```bash
   pip install -r training/requirements.txt
   python training/train_whisper_lora.py \
       --manifest training/data/cv-fa/manifest.jsonl \
       --output training/runs/whisper-small-fa-lora \
       --epochs 3
   ```

   The eval callback normalizes both reference and hypothesis with the
   product's own `normalize_persian`, so the logged WER is directly
   comparable to `benchmarks/benchmark_wer.py`.

3. **Convert.** Merge the adapter, then produce a CTranslate2 model:

   ```bash
   ct2-transformers-converter \
       --model training/runs/whisper-small-fa-lora/merged \
       --output_dir models/whisper-small-fa-ct2 \
       --quantization float16
   ```

4. **Serve + re-benchmark.** Point `WHISPER_MODEL_SIZE` at
   `models/whisper-small-fa-ct2` and re-run
   `python benchmarks/benchmark_wer.py --models <that-dir>` to compare
   against the published baseline table.

## What is *not* done yet

- No training run has happened: this repo has no GPU runner, and no numbers
  about a fine-tuned model exist yet. When the first run finishes, its WER
  table goes into `benchmarks/` next to the baseline — measured, never
  promised.
- The default eval split (2%) is small; a proper report should freeze a
  larger, speaker-disjoint hold-out.
- Data augmentation (noise, speed perturbation) is a known next step for
  colloquial robustness — the baseline benchmark shows exactly where it
  hurts.
