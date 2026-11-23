# Changelog

All notable changes to Sokhan are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/) and the project versions with [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- A **GitHub Pages landing page** ([site/](site/), live at
  [abolfazlrwm.github.io/sokhan](https://abolfazlrwm.github.io/sokhan/)):
  a Persian-first, RTL, dark one-pager with the measured numbers, the
  benchmark table, screenshots, the quickstart and the architecture chain —
  auto-deployed from `main` by the new `pages.yml` workflow (Pages enabled
  with `build_type: workflow`), so the shareable link never drifts from the
  repo. It ships a 1200×630 `og-image.png` for embeds
- **Coverage measurement in CI**: the test job now runs under
  `pytest-cov` with branch coverage over `sokhan` + `sokhan_bot`
  (78.2% lines / 264 of 396 branches on the non-GPU suite at the time of
  writing) and appends a per-file markdown table to the job summary via
  `scripts/coverage_summary.py`; `pytest-cov` joins the `dev` extra
- A `dependabot.yml` that keeps pip (backend, bot), npm (web),
  github-actions and docker dependencies on weekly update PRs (minor/patch
  grouped to reduce noise), plus a pull-request template with the
  measurement-first checklist

### Fixed

- The README's "honest limits" and roadmap sections still described
  streaming decode and signed webhooks as *open* roadmap items after they
  had shipped in v1.3.0; they now state the shipped facts (86.4 MB vs
  355.6 MB peak RAM on a 30-minute file, `STREAMING_DECODE` on by default,
  `callback_url` + `X-Sokhan-Signature` webhooks), and the features list
  and Docker badge were brought in sync

## [1.3.0] - 2026-11-23

### Added

- **Streaming decode in the worker** (roadmap v1.4): the pipeline no longer decodes
  the whole recording to memory before chunking. `core/audio.py` streams
  PyAV blocks resampled to mono 16 kHz and `core/chunking.py::iter_chunks`
  emits the same 30-second windows from the block stream — `test_streaming.py`
  proves both paths produce identical chunks, including the short-tail fold.
  Measured on identical 16 kHz mono WAVs (whole-process peak RSS, ~28 MB of
  it interpreter baseline): a 30-minute file peaks at **86.4 MB streamed vs
  355.6 MB fully decoded (4.1x lower)**; a 10-minute file at 84.9 MB vs
  169.6 MB. Full decode still grows linearly with duration, streaming stays
  flat — multi-hour recordings no longer need RAM proportional to file size.
  Diarization engines that need the whole signal (energy, pyannote) declare
  `requires_full_audio` and take the legacy path automatically; behind
  `STREAMING_DECODE` (default on)
- **Signed job-completion webhooks** (roadmap v1.5): `POST /jobs` accepts an optional
  `callback_url` (http/https, ≤ 2048 chars, echoed on the job detail). When
  the job completes or fails, the worker POSTs a JSON event (event,
  job_id, status, language, duration, text excerpt capped at 4000 chars,
  transcript_url, error) signed Stripe-style:
  `X-Sokhan-Signature: t=<unix>,v1=<hex hmac-sha256(secret, "<ts>.<body>")>`
  with `X-Sokhan-Timestamp`; receivers re-compute, compare with
  `hmac.compare_digest` and drop anything older than five minutes.
  `WEBHOOK_SIGNING_SECRET` turns signing on (empty sends unsigned), delivery
  retries once with a 4 s timeout and never flips the job's final status —
  a dead callback endpoint is logged, not fatal. Migration 0003 adds
  `jobs.callback_url`
- **Persian punctuation restoration** (roadmap v1.4): a deterministic rule-based
  post-pass in the worker pipeline turns the raw Whisper word stream into
  publishable text — `؟` on question sentences (آیا/چرا/چطور/کجا/…), `.` on
  the rest, Latin `,`/`;`/`?` mapped to ،/؛/؟, no space before marks and one
  space after, decimals (`3.5`) and clock times (`12:30`) left intact.
  Behind `PUNCTUATION_ENABLED` (default on); the WER benchmark path is
  untouched so measured numbers stay comparable, and archive search gained
  `normalize_for_search` (punctuation stripped on column and query) so
  phrase queries match the punctuated text. The browser demo ports the same
  rule family, so the Space shows transcripts in the product's shape
- **Confidence-aware review flags** (roadmap v1.5): the engine's exp(avg_logprob) is
  now persisted per segment (Alembic migration 0002 adds
  `segments.confidence`), flows through `GET /jobs/{id}`, the JSON export
  and `verbose_json`, and spans below `LOW_CONFIDENCE_THRESHOLD` (default
  0.5) are marked `⚠` in the SRT/VTT/DOCX exports and badged
  "نیاز به بازبینی / Needs review" in the dashboard timeline — reviewers
  re-listen exactly where the model was unsure
- **Prebuilt Docker images on GHCR** (roadmap v1.5): a `docker.yml` workflow builds
  and pushes `ghcr.io/abolfazlrwm/sokhan-api` and
  `ghcr.io/abolfazlrwm/sokhan-web` on pushes to `main` and on version tags
  (`latest`, `sha-*`, semver), so self-hosting can run published images
  instead of building; the compose file references the same names next to
  its `build:` blocks and the README documents the pull path
- The compose file now passes `WHISPER_BEAM_SIZE` and
  `WHISPER_INITIAL_PROMPT` through to the containers (the engine knobs
  shipped earlier but were unreachable in a compose deployment) plus the
  two new `PUNCTUATION_ENABLED` / `LOW_CONFIDENCE_THRESHOLD` variables

- A public **browser demo** (`space/`): a free Static Space where Whisper
  runs entirely client-side (transformers.js, ONNX q8, base/small
  selectable, RTL Persian UI, bundled benchmark sample clip — a headless
  browser verified it end to end: 3.5 s clip transcribed in 5.0 s
  on-device); plus `space/gradio/`, a self-hostable Gradio app serving the
  fine-tuned checkpoint with the production engine config — HF's 2026
  pricing gates hosted Gradio/Docker Spaces behind a PRO subscription
  (402 on create), which is why the free Space is the static page
- A proper **Hugging Face model card** (`training/model_card.md`),
  published to the whisper-small repo with the measured WER/CER, honest
  caveats (12-clip fixture, 500-clip training set), usage snippet and full
  reproduction instructions
- `docs/ROADMAP.md` — versioned phases (v1.3 public face, v1.4 engine
  quality, v1.5 product surface, v2.0 candidates) under the
  measurement-first rule
- `.pre-commit-config.yaml` for contributors (ruff + hygiene hooks)
- A `Sync demo Space` workflow: pushes that touch `space/` are
  auto-published to the live Space by `deploy/sync_space.py` (HF token
  kept in the repo's `HF_TOKEN` Actions secret), so the public demo can
  never drift from `main`; CONTRIBUTING.md and issue templates round out
  the contributor surface
- The **segments timeline** in the API: `GET /jobs/{id}` now returns the
  per-segment transcript (start / end / speaker / text, 1-based position)
  the database always stored but never exposed, and the dashboard renders
  it as a timestamped, speaker-labelled transcript view instead of a flat
  paragraph
- Two more **transcript exports**: WebVTT (also on the OpenAI-compatible
  endpoint, completing its `response_format` set: json / text / srt / vtt /
  verbose_json) and structured JSON with the full segment list
- Dashboard **actions**: copy the transcript to the clipboard and delete a
  transcription with a confirmation — the `DELETE /jobs/{id}` endpoint
  existed and was tested, but no UI button called it
- Engine **decoding knobs**: `WHISPER_BEAM_SIZE` (default 5, matching the
  benchmark and demo config) and `WHISPER_INITIAL_PROMPT` for a domain
  lexicon so names and technical terms survive (v1.4 roadmap item)
- The Telegram bot **keeps its promise now**: a completion notifier
  (`sokhan_bot.notify`) watches every job the bot submits — persisted
  across restarts — and pushes the transcript in Telegram-sized chunks
  (or a failure notice) the moment the backend finishes; jobs stuck over
  six hours are released with a note instead of leaking
- A **weekly benchmark gate**: the fixture runs every Monday against the
  recorded baseline (`benchmarks/results/baseline.json`) and fails CI if
  the `small` engine loses more than one WER point; the script gained
  `--archive`, `--baseline` and `--max-regression` flags (gate logic in
  `benchmarks/regression.py`, no heavy imports, fully unit-tested)

### Fixed

- The bot's welcome text and upload reply always said the transcript
  would be sent "as soon as it is ready" — but nothing ever sent it;
  the completion notifier above actually delivers it now

### Security

- Patched the four PostCSS advisories flagged by Dependabot (arbitrary
  file read via attacker-controlled `sourceMappingURL`, path traversal in
  source-map auto-loading, the incomplete-fix follow-up, XSS via unescaped
  `</style>` in stringify output) by forcing `postcss ^8.5.23` under
  `next` through npm `overrides` and refreshing the lockfile; verified
  with a clean `next build` (all routes compile, Tailwind pipeline
  unaffected). `next` stays on 15.5 — the audit's `--force` path would
  have been a major-version upgrade
- picomatch ReDoS (GHSA-fc5q-39xc-vjpf) currently has **no upstream fix**:
  the vulnerable range `<= 4.0.7` includes the latest published release.
  The chain is `next-intl → @parcel/watcher → picomatch`, exercised only
  by dev-time file watching over globs defined in this repo, not by
  anything attacker-controlled in production. The Dependabot alert is
  dismissed as `tolerable_risk` with that reasoning recorded on the alert
  itself, and gets reopened the day upstream ships a patched picomatch

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
