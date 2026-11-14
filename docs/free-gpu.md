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
2. Run the cells top to bottom. The training data (cell 5) is a public CC-0
   Persian Common Voice mirror, so no Hugging Face account is needed until
   you want to push the converted model to the Hub in cell 9 (a write token
   then, not a read token).
3. The pipeline itself was verified without a GPU first
   (`python training/smoke_test.py`) and a real CPU fine-tune of
   `whisper-tiny` on 518 mirror clips was executed end to end on 2026-11-15
   (see `benchmarks/README.md`), so failures are data or quota issues, not
   script issues.
4. First run small (`MAX_HOURS=5`, `MAX_SAMPLES=3000`) to learn the loop and
   timings on the specific GPU you got, then scale up across sessions.

Keep artifacts outside the volatile session disk: download the converted
CT2 folder (cell 9 zip) or push it to the Hugging Face Hub — the notebook has
both options.

## Colab error: "Failed to assign a backend … restriction in your location"

Colab refuses GPU backends to IPs from sanctioned regions (Iran, Syria, …).
Nothing is wrong with the notebook — Google blocks the connection before any
cell runs. Two fixes, in order:

1. **Colab + VPN.** Connect a VPN with an exit outside the blocked regions
   (e.g. Türkiye, UAE, Germany), then open a fresh incognito window, sign in
   to Google again, and reload the notebook. The bottom-right badge should
   turn to "Connected (T4 GPU)". If the error persists, the VPN's exit IP is
   flagged by Google — switch servers and retry. Some VPN exits work for
   browsing but not for backend assignment, so try more than one.
2. **Kaggle, usually without a VPN.** Kaggle is normally reachable from Iran
   and gives 2× T4 or a P100:
   1. Sign in at [kaggle.com](https://www.kaggle.com) with a Google account.
   2. Verify a phone number (Settings → Phone verification); GPU + Internet
      access is disabled until this passes. If the SMS never arrives for your
      SIM, this lane is closed — fall back to option 1.
   3. Code → New Notebook → File → **Import Notebook** → paste the GitHub URL
      `https://github.com/Abolfazlrwm/sokhan/blob/main/training/finetune_fa_colab.ipynb`.
   4. Right panel: Accelerator → **GPU T4 x2**, Internet → **On**.
   5. Run the same cells top to bottom. The save cell is guarded against
      `google.colab` imports, so zip mode falls back to printing the file
      path on Kaggle; prefer `SAVE_MODE = "hf_hub"` there anyway.

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
  script saves a checkpoint every 150 optimizer steps in `--output`, so a
  killed session loses at most a few minutes; re-run with the same output
  directory and `--resume` to continue from the last saved checkpoint.
- No accuracy claim lives in this file. The first CPU-scale fine-tune
  (2026-11-15, `whisper-tiny`, 45 minutes of data) measured **no WER
  improvement** — its rows and conclusions live in `benchmarks/README.md`.
  The GPU-scale run (`whisper-small`, hours of data) is the experiment that
  can actually move the number; when it finishes, run
  `python benchmarks/benchmark_wer.py --models <dir-or-repo-id>` on the
  same 12-clip Common Voice fixture and add the measured row next to the
  baseline — measured numbers only, never promised ones.
