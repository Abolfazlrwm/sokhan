# Fine-tuning without your own GPU

You do not need to own a GPU to fine-tune Persian Whisper for Sokhan. The
LoRA pipeline (`training/`) trains `whisper-small` inside a 16 GB VRAM
budget, which every platform below gives away for free. Facts checked
2026-11-14; free tiers change, so re-check before planning long runs.

## Where to get free GPU time

| platform | free allotment | hardware | session cap | best for |
| --- | --- | --- | --- | --- |
| [Google Colab](https://colab.research.google.com) (free tier) | dynamic, not published | T4 16 GB | ~12 h, idle timeouts | the quickest start; `training/finetune_fa_colab.ipynb` opens directly |
| [Kaggle Notebooks](https://www.kaggle.com/code) | ~30 GPU-hours/week, published in your account settings | P100 or 2× T4 | 12 h | longer runs; the most predictable quota; runs the same notebook |
| [Lightning AI Studio](https://lightning.ai) | ~15 free credits/month (~22 T4-hours) | T4 class | per-session | a second free lane when Colab/Kaggle quotas run dry |

Combined, Colab + Kaggle give you roughly 30–60 free GPU-hours per week with
no credit card. Start with Kaggle for anything longer than an hour: its
allowance is published, its sessions can run with the browser tab closed, and
it supports scheduled notebooks. Colab's free quota fluctuates and it stops
when you close the tab.

## How to run the Persian fine-tune on them

1. Open `training/finetune_fa_colab.ipynb` in Colab (or upload the same file
   to Kaggle and switch the accelerator on).
2. Accept the conditions of the gated Common Voice dataset with a free
   Hugging Face account and paste a read token (cell 4 does the prompts).
3. Run the cells top to bottom. The pipeline itself was verified without a
   GPU first (`python training/smoke_test.py`), so failures are data or quota
   issues, not script issues.
4. First run small (`MAX_HOURS=5`, `MAX_SAMPLES=3000`) to learn the loop and
   timings on the specific GPU you got, then scale up across sessions.

Keep artifacts outside the volatile session disk: download the converted
CT2 folder (cell 9 zip) or push it to the Hugging Face Hub — the notebook has
both options.

## Free hosting for the result

- **Weights:** Hugging Face Hub hosts public model repos for free; the
  notebook's `hf_hub` mode uploads `whisper-small-fa-ct2` directly.
- **A live demo:** a free Hugging Face Space (2 vCPU) can run Sokhan's API +
  dashboard container with the `tiny` model on CPU — enough to demo
  transcription without paying. The conversion recipe in
  `training/README.md` works unchanged.
- **Self-hosting:** the existing `deploy/docker-compose.yml` stays the
  primary path; point `WHISPER_MODEL_SIZE` at your converted model folder.

## Honest notes

- Free tiers are best-effort: you can be preempted mid-run. The training
  script saves per-epoch checkpoints in `--output`, so a killed session does
  not necessarily mean lost work; re-run with the same output directory to
  resume from the last saved checkpoint.
- No accuracy claim lives in this file. When the first fine-tuned model
  finishes, run `python benchmarks/benchmark_wer.py --models <dir>` on the
  same 12-clip Common Voice fixture and add the measured row next to the
  baseline in `benchmarks/README.md` — measured numbers only, never promised
  ones.
