# Persian Whisper fine-tuning

A complete, runnable pipeline to adapt a Whisper checkpoint to Persian speech
and convert it back into the faster-whisper format Sokhan actually serves.

**Status: verified end-to-end, no GPU required to validate.** The chain
`prepare → LoRA train → merge → CTranslate2 convert` runs green on CPU
(`whisper-tiny`, 8 synthetic clips, a few seconds per epoch) — every script in
here has actually executed and produced artifacts. Run
`python training/smoke_test.py` to confirm the same on your machine before
starting a real run.

## What exists today

| file | purpose |
| --- | --- |
| `prepare_common_voice.py` | filters a Common Voice (fa) release into a training manifest (JSONL) |
| `train_whisper_lora.py` | LoRA fine-tune of a Whisper checkpoint with epoch-wise Persian WER evaluation |
| `smoke_test.py` | one-command CPU verification of the whole chain, no GPU needed |
| `finetune_fa_colab.ipynb` | one-click Google Colab notebook: data → train → convert → download, on a free T4 |
| `requirements.txt` | the training-only dependency set |

## No GPU? Train on a free one

You do not need your own GPU. Verified options (2026-11):

| platform | free allotment | hardware | notes |
| --- | --- | --- | --- |
| Google Colab (free) | dynamic quota, not published | T4 16 GB | fastest to start; sessions can stop at ~12 h / idle timeouts |
| Kaggle Notebooks | ~30 GPU-hours/week, published | P100 or 2×T4 | most predictable; 12 h sessions; works with the same notebook |
| Lightning AI Studio | ~15 free credits/month (~22 T4 h) | T4 | notebook UX closest to Colab |

Details and tips: [docs/free-gpu.md](../docs/free-gpu.md). The Colab notebook
also runs on Kaggle — upload it there and select a GPU accelerator.

## Why LoRA

Full fine-tuning of `whisper-small` (~244 M parameters) in fp32 needs memory
most self-hosters do not have. LoRA freezes the base weights and trains small
rank-decomposed adapters on the attention projections instead, which brings
the memory requirement down to a single consumer GPU (8–16 GB) while keeping
the model convertible back to a dense checkpoint. A free T4's 16 GB is enough.

## The loop, end to end

1. **Data.** Point the notebook (or this script) at a Common Voice Persian
   release (CC-0). The preparer keeps clips with community consensus (two or
   more up-votes, no down-votes) and sane durations:

   ```bash
   python training/prepare_common_voice.py \
       --cv-root ~/datasets/cv-corpus-XX.X-YYYY-MM-DD/fa \
       --output training/data/cv-fa/manifest.jsonl \
       --max-hours 100
   ```

   Real Common Voice releases ship no `duration` column, so the script reads
   audio headers with soundfile — no full decode.

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
   against the published baseline table. Measured numbers go into
   `benchmarks/` — never promised ones.

## Bugs found and fixed while verifying (2026-11-14)

The pipeline was executed end to end on CPU; three real incompatibilities
with the current ML stack surfaced and are fixed:

- `torchaudio.load` now requires the TorchCodec layer — audio loading moved
  to `soundfile`, which reads Common Voice formats without a codec backend
- `Dataset.map` round-trips tensors through Arrow, so the collate function
  rebuilds them with `torch.as_tensor` before stacking
- transformers ≥ 5 accepts the language name `persian`, not `farsi`

## What is *not* done yet

- No *real* training run has happened: this repo has no GPU runner, so no
  fine-tuned WER numbers exist yet. When the first run finishes on a free
  GPU, its measured table goes into `benchmarks/` next to the baseline.
- The default eval split (2%) is small; a proper report should freeze a
  larger, speaker-disjoint hold-out.
- Data augmentation (noise, speed perturbation) is a known next step for
  colloquial robustness — the baseline benchmark shows exactly where it
  hurts.
