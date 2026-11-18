# Changelog

All notable changes to Sokhan are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/) and the project versions with [Semantic Versioning](https://semver.org/).

## [1.2.0] - 2026-11-18

### Added

- The first **GPU-scale** fine-tune, measured and published (2026-11-18):
  LoRA on `whisper-small`, 500 Common Voice (fa) clips / ≈45 minutes of
  speech, 3 epochs in ~7 minutes on a free Colab T4 — training loss
  3.63 → 1.75, held-out eval WER 85.1% → 81.6%, and on the 12-clip fixture
  **WER 80.5% → 79.3% / CER 26.7% → 24.9%** — the first fine-tune to beat
  its own baseline. Artifact:
  `hf.co/Abol0pati/whisper-small-fa-sokhan`; the benchmark row and its
  honest caveats live in `benchmarks/README.md`
- The benchmark table now carries all five models (three baselines + two
  fine-tuned checkpoints) measured back to back in one session, with the
  2026-11-13 and 2026-11-15 sessions archived in `benchmarks/results/`
- The first real fine-tune run, measured end to end on CPU (2026-11-15):
  LoRA on `whisper-tiny`, 518 Common Voice (fa) clips / 45 minutes from the
  public CC-0 mirror's train split, 2 epochs — training loss 3.84 → 1.55,
  held-out WER flat at 94.6%, fixture WER 103.7% vs 92.7% untuned. The
  converted artifact is published at
  `hf.co/Abol0pati/whisper-tiny-fa-sokhan` so anyone can re-run its
  benchmark row; the honest conclusion (no WER gain at CPU scale, GPU-scale
  `whisper-small` run required) is documented in `benchmarks/README.md`
- Step-based training checkpoints (every 150 steps, keep 2): preempted
  free-GPU sessions resume from the last ~3-minute boundary instead of the
  last epoch
- Speaker diarization engines behind `DIARIZATION_ENGINE`: a dependency-free
  `energy` clusterer and a `pyannote` neural adapter (falls back gracefully
  to the stub), wired through the transcription pipeline into SRT/DOCX
  exports (ADR 0004)
- Fine-tuning pipeline verified end-to-end on CPU: `training/smoke_test.py`
  proves the whole chain (manifest prep → LoRA train → merge → CTranslate2
  convert) in about a minute; the three incompatibilities it caught with the
  current ML stack (TorchCodec-backed `torchaudio.load`, Arrow tensor
  round-trips, transformers ≥ 5 language name) are fixed
- `--resume` on the trainer: free-GPU sessions that get preempted continue
  from the last checkpoint
- `training/finetune_fa_colab.ipynb` — one-click Colab notebook that runs
  data → train → convert → serve/download on a free T4 (Kaggle works too)
- `docs/free-gpu.md` — verified free GPU options for the first real
  fine-tuning run (Colab T4, Kaggle ~30 GPU-h/week, Lightning AI)
- `docs/free-gpu.md` documents the "Failed to assign a backend —
  restriction in your location" Colab error (sanctioned-region IPs) with
  the VPN-reload and Kaggle-import fixes, so users in Iran can actually
  reach a free GPU
- `SECURITY.md` with a private vulnerability-reporting channel

### Fixed

- The Colab install cell uninstalls Colab's preinstalled `torchao` 0.10,
  which made `peft` hard-fail LoRA injection even though the pipeline
  never imports torchao ("only versions above 0.16.0 are supported")
- The install cell prints `training deps OK` after installing: the smoke
  test skips its ct2/faster-whisper leg when a package is missing, so a
  silently failed `pip install faster-whisper` used to surface only later
  as `ModuleNotFoundError` in the serving cell
- The serving-test cell fails with a readable message when the converted
  folder is absent (faster-whisper otherwise raises a cryptic "Invalid
  model size" ValueError), and falls back to CPU int8 when a VM ships
  incomplete CUDA 12 user-space libraries ("libcublas.so.12 is not
  found") — the configuration the backend deploys anyway
- The notebook's save cell guards the `google.colab` import, so the same
  notebook runs on Kaggle (zip mode prints the file path instead of
  crashing)

- The Colab notebook's data cell used `mozilla-foundation/common_voice_17_0`,
  which no longer ships data files (verified 2026-11-15: only README and
  `.gitattributes` remain in its repo tree) and whose loading script is
  unsupported since `datasets` 3 — the notebook now streams the public CC-0
  parquet mirror `pymmdrza/Common-Voice-Speech-26.0-Persian-Clean`, train
  split only, no token or gating needed
- `benchmarks/requirements.txt` pins `av<14` (same as the backend):
  faster-whisper 1.2.1 calls `av.open(..., metadata_errors=...)`, which
  PyAV ≥ 15 removed, so a fresh benchmark install would crash on every clip
- The diarization tests referenced a `fake_engine` fixture that was defined
  only in one test module; it now lives in the shared conftest so the full
  engine/pipeline coverage actually runs

## [1.1.0] - 2026-11-13

### Added

- Reproducible WER benchmark on 12 real Common Voice (fa) clips, shipped with
  the audio, references, script and full per-clip results
- Real end-to-end product demo recorded from the running web dashboard
  (`docs/assets/demo.gif`)
- README accuracy section reporting measured WER/CER for tiny/base/small
- Persian Whisper fine-tuning pipeline (`training/`): Common Voice (fa) manifest
  preparation, LoRA training script with Persian-normalized WER evaluation and
  CTranslate2 conversion instructions (first training run pending GPU)

### Changed

- Web fonts (Vazirmatn, Inter) are self-hosted now; `next build` no longer
  needs to reach Google Fonts, removing a flaky network step from CI and
  enabling offline builds

## [1.0.0] - 2026-11-13

### Added

- docker compose for one-command self-hosting (api, worker, redis, postgres, web)
- Dockerfiles for the backend and the web dashboard (standalone build)
- Alembic initial migration plus a runtime URL override for DATABASE_URL
- ADR 0003 (diarization interface) and docs/architecture.md
- README with self-hosting guide, configuration table, API surface and roadmap

## [0.2.0] - 2026-11-13

### Added

- Next.js dashboard with Persian-first (RTL) and English locales
- Landing page, login/registration and connect-code entry
- Upload and in-browser recording with language and summary options
- Archive with Persian-normalized search and status badges
- Job detail page with live progress and TXT/SRT/DOCX downloads

## [0.1.0] - 2026-11-13

### Added

- Audio decoding and 30-second chunking with a 1-second overlap
- faster-whisper transcription engine (CPU, int8) plus a deterministic fake engine for tests
- Smart segment merging across chunk boundaries with timestamp clamping
- TXT, SRT and DOCX exports
- OpenAI-compatible POST /v1/audio/transcriptions endpoint
- Monthly usage tracking and quota enforcement (HTTP 402)
- Speaker diarization interface with a stub implementation

### Fixed

- PyAV pinned below 14 (newer majors removed an API faster-whisper's decoder uses)
