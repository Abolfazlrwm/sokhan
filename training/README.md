# Persian Whisper fine-tuning

A complete, runnable pipeline to adapt a Whisper checkpoint to Persian speech
and convert it back into the faster-whisper format Sokhan actually serves.

**Status: verified end-to-end, with and without a real GPU.** The chain
`prepare → LoRA train → merge → CTranslate2 convert` runs green on CPU
(`whisper-tiny`, 8 synthetic clips, a few seconds per epoch), and on
2026-11-15 the same chain executed against *real* Persian data: 518 Common
Voice (fa) clips / 45 minutes, trained, converted, served through
faster-whisper and benchmarked (measured rows in `benchmarks/README.md` —
no WER gain at CPU scale, honestly documented there). Run
`python training/smoke_test.py` to confirm the chain on your machine before
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

1. **Data.** The Colab notebook (cell 5) streams the *train* split of
   `pymmdrza/Common-Voice-Speech-26.0-Persian-Clean` — a public, CC-0,
   parquet-based Persian Common Voice subset (cv-corpus-26.0), the same
   release the benchmark fixture comes from. It needs no account, no token,
   no gating.

   Do **not** use `mozilla-foundation/common_voice_17_0` any more: verified
   2026-11-15, its repo no longer ships data files, and script-based loaders
   are unsupported since `datasets` 3.

   For offline Common Voice releases (tsv + clips on disk) the preparer
   still works and keeps clips with community consensus (two or more
   up-votes, no down-votes) and sane durations:

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

## Bugs found and fixed while verifying (2026-11-14 / 2026-11-15)

The pipeline was executed end to end on CPU; real incompatibilities with the
current ML stack surfaced and are fixed:

- `torchaudio.load` now requires the TorchCodec layer — audio loading moved
  to `soundfile`, which reads Common Voice formats without a codec backend
- `Dataset.map` round-trips tensors through Arrow, so the collate function
  rebuilds them with `torch.as_tensor` before stacking
- transformers ≥ 5 accepts the language name `persian`, not `farsi`
- `mozilla-foundation/common_voice_17_0` ships no data files any more and
  script datasets are dead in `datasets` ≥ 3 — the notebook now streams the
  public CC-0 mirror `pymmdrza/Common-Voice-Speech-26.0-Persian-Clean`
  (found by actually running the data cell, not by reading docs)
- faster-whisper 1.2.1 + PyAV ≥ 15 is a broken combination (`av.open` lost
  `metadata_errors`) — the benchmark pins `av<14`, same as the backend
- the trainer now checkpoints every 150 steps (not only per epoch), so a
  preempted session loses at most ~3 minutes of work

## What is *not* done yet

- The GPU-scale run exists (2026-11-18, free Colab T4): `whisper-small` +
  LoRA on 500 clips / ≈45 minutes of speech, 3 epochs in ~7 minutes —
  under the v1 harness that was fixture WER 80.5% → 79.3%; re-measured
  under the v2 harness (orthography prompt + polish, see
  `benchmarks/README.md`) it lands at 75.0%. Real, but small; the same
  notebook at `MAX_SAMPLES = 0` (the full 10-hour manifest, ~1.5–2 h on a
  T4) is the next run, ideally paired with a larger speaker-disjoint
  hold-out than the default 2% eval split.
- **Next-level run (recommended): LoRA on `whisper-medium`.** The measured
  untuned gap (small 75.0% vs medium 56.2% WER under v2) shows the base
  model is the bottleneck, not the adapter size. The same notebook with
  `MODEL_NAME = "openai/whisper-medium"` fits a free T4 (~1.5 GB LoRA
  state in int8 bf16); even 2–3 hours of Persian speech there should
  undercut every `small`-class number by a wide margin.
- To put the fine-tuned engine **inside the browser demo**, run
  [export_web_onnx.py](export_web_onnx.py) (merge → ONNX → int8 → Hub) on
  Colab and add the resulting repo id to `space/index.html`. No new demo
  code is needed — the worker loads any Xenova-style whisper repo.
- The default eval split (2%) is small; a proper report should freeze a
  larger, speaker-disjoint hold-out.
- Data augmentation (noise, speed perturbation) is a known next step for
  colloquial robustness — the baseline benchmark shows exactly where it
  hurts.
