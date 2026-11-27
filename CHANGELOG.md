# Changelog

All notable changes to Sokhan are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/) and the project versions with [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Security

- **`POST /auth/telegram` could be used to take over any Telegram user's
  account.** It minted a fresh API token for whatever `telegram_id` the
  caller sent, with no proof the caller was the bot. It now requires the
  `X-Bot-Secret` header to match the new `BOT_API_SECRET` (constant-time
  compare; 403 on mismatch, 503 while unset). **Breaking for deployments
  with the bot:** set the same `BOT_API_SECRET` on the API and the bot; the
  bot refuses to start without it.
- Request bodies above `MAX_UPLOAD_MB` (plus 1 MiB multipart allowance) are
  now refused with 413 by a middleware, up front from `Content-Length` or
  mid-stream for chunked uploads. Before, the size check ran only after the
  whole body had been spooled to disk and read into memory, so one
  multi-gigabyte upload could exhaust the API container's disk or RAM.
- Webhook `callback_url`s can no longer target internal addresses. Any
  user could point the worker at loopback, private, link-local (cloud
  metadata) or LAN hosts. Literal private hosts are now rejected at upload
  (422), every resolved address is checked again at connect time (defeating
  DNS rebinding), redirects are not followed and proxy env vars are ignored.
  **Breaking for receivers on private addresses:** set
  `WEBHOOK_ALLOW_PRIVATE_TARGETS=true` on trusted single-tenant installs.
- `POST /auth/login` is throttled: after `LOGIN_MAX_FAILURES` (10) failures
  per client address and email within `LOGIN_FAILURE_WINDOW_SECONDS` (900)
  it answers 429 with `Retry-After`; a successful login clears the count.

### Fixed

- Compose: the Whisper model cache now lives on the `sokhan-data` volume
  (`HF_HOME=/data/huggingface`). Previously it sat in the container's own
  filesystem, so every recreate (`down`/`up`, `--build`, a new image)
  re-downloaded the weights — and transcription failed outright where the
  Hugging Face Hub is unreachable.
- Compose: the postgres healthcheck probes the configured `POSTGRES_USER` and
  `POSTGRES_DB` instead of a hardcoded `sokhan`.
- Quickstart (both READMEs) and `.env.example` now say to copy the env file to
  `deploy/.env`; the missing-password error names that path too. Copying it to
  the repo root left `POSTGRES_PASSWORD` unset for compose.

### Added

- **Persian accuracy stack (v2)** — measured on the 12-clip Common Voice
  fa fixture, every number reproducible:
  - New `sokhan.core.fa_polish` module: orthographic-only Persian ASR
    repair (ZWNJ prefix/suffix fusion, split-imperative repair like
    "بی پوش" → "بپوش", Arabic look-alike code points, Latin→Persian
    digits, punctuation spacing). Wired into the pipeline behind
    `FA_POLISH=true` and ported verbatim to the browser demo
    (16-case parity test with the Python implementation). Measured
    −3.6 WER points; never rewords colloquial speech.
  - New default `whisper_initial_prompt`: a ZWNJ-correct Persian
    orthography prompt. whisper copies prompt script style — measured
    −1.3 WER points on `small`, −4.8 on the fine-tuned checkpoint.
  - **Default engine is now `medium`**: 56.2% WER vs 75.0% for `small`
    under the v2 harness — a −24.3-point jump at ~1.1x realtime on 2 CPU
    cores (int8, ~800 MB download). `WHISPER_MODEL_SIZE=small` remains
    the documented speed-first profile.
  - Browser demo: default model switched base → small (fixture 90.2% →
    75.0% under v2), output now passes through the same polish pass as
    the server, and the honesty note was updated.
  - `benchmarks/tune_decode.py`: the decode sweep harness the decisions
    above came from (prompt variants × beam × VAD ×
    condition_on_previous_text).
  - `training/export_web_onnx.py`: merge-LoRA → ONNX → int8 → HF Hub
    pipeline that produces a transformers.js-compatible repo of any
    Sokhan fine-tune, so the browser demo can run the project's own
    engine once the export runs on Colab.
  - `baseline.json` regenerated under the v2 harness (small 0.75 /
    fine-tuned 0.75 / medium 0.5625); the weekly benchmark workflow now
    guards `small` **and** `medium`; regression-gate test updated to the
    committed baseline.
- Dashboard dark mode: a sun/moon toggle in the header, defaulting to the OS
  preference until the user picks one (saved in localStorage, applied before
  first paint so there is no flash). Implemented by remapping the Tailwind
  palette under `html.dark` in `globals.css`, so existing pages needed no
  per-class changes.
- Brand refresh: a hero banner in both READMEs (`docs/assets/banner.png`),
  a redesigned 1280x640 social preview (`docs/assets/social-preview.png` —
  upload it once in Settings → General → Social preview) and a 512px app
  icon (`docs/assets/icon-512.png`) usable as the HF Space avatar. The
  landing site og:image was regenerated in the same style.
- Browser demo speed & UX overhaul (space/): WebGPU fast path (fp32
  encoder + q4 decoder) with automatic WASM/q8 fallback, per-window
  transcription progress with an ETA and elapsed timer, a real cancel
  button (terminates the worker; the model stays in browser cache), a
  timestamped line-by-line transcript toggle, a copy button and stage
  pills. The windowing (30 s window / 5 s overlap) now lives in the
  worker with timestamp-midpoint trimming, enabling the progress stream
  and duration caps: 30 min on WebGPU, 10 min on WASM, 60 MB per file —
  no input can wedge the demo at an eternal "processing" state anymore.

### Changed

- **Demo hang fix**: audio was decoded inside an `AudioContext` forced to
  16 kHz; Chromium can hang forever on opus/webm (Telegram voice,
  MediaRecorder) in that configuration — the demo sat at "در حال
  آماده‌سازی صدا" indefinitely. Decoding now happens at the context's
  natural rate and is resampled offline to 16 kHz, with a 45 s decode
  watchdog and clear format-error messages (e.g. OGG on Safari). The
  worker's origin guard also now accepts the EMPTY `event.origin`
  Chromium 158+ posts for same-origin dedicated-worker messages — the
  strict comparison silently rejected every command and left the demo
  at "در حال پردازش" forever.

- **License: MIT → PolyForm Noncommercial 1.0.0 (source-available).** The
  code stays readable and reviewable by anyone, and noncommercial use
  (personal projects, study, research, nonprofits) remains free; any
  commercial use now requires a paid license from the author. Releases up
  to and including v1.4.1 (2026-11-26) were published under MIT and remain
  under it. Applied across LICENSE, both READMEs, CITATION.cff, both
  pyproject.toml files, web/package.json, the landing site copy, the demo
  Space metadata and the fine-tuned model card.

## [1.4.1] - 2026-11-26

### Security

- First CodeQL run surfaced five findings; all triaged with a written
  policy (see SECURITY.md, "Code scanning policy"):
  - **Fixed** `py/polynomial-redos` — the email validation regex
    `^[^@\s]+@[^@\s]+\.[^@\s]+$` backtracked polynomially on long
    dot-less inputs (a 200k-char request could burn minutes of CPU per
    attempt). Replaced with an unambiguous pattern plus an RFC-5321
    length cap (254); a pathological 200k-char address now matches in
    ~8 ms. All 10 auth tests pass unchanged.
  - **Fixed** `js/missing-origin-check` — the demo worker now drops
    `postMessage` commands whose origin is not the page that created it
    (defense in depth; cache-bust bumped to `?v=3`).
  - **Dismissed with justification** `py/weak-sensitive-data-hashing`
    (API tokens are high-entropy; SHA-256 token hashing is the standard
    storage, passwords use scrypt), `js/clear-text-storage-of-sensitive-data`
    (SPA localStorage trade-off; httpOnly-cookie migration is tracked as
    roadmap work), and `py/path-injection` in the Gradio demo (the path
    is produced by Gradio's upload pipeline, not raw client input).

### Added

- **Release automation**: pushing a `v*` tag extracts the matching
  CHANGELOG section (`scripts/extract_release_notes.py`) and creates or
  updates the GitHub Release — the changelog stays the single source of
  truth; this release is the first cut by that pipeline
- **OpenSSF Scorecard** workflow (weekly + per-push, `publish_results`)
  grading the supply-chain posture, with the public badge in both READMEs
- **SBOM + max-mode provenance attestations** on every GHCR image push —
  verifiable with `docker buildx imagetools inspect`
- **Compose integration smoke test** in CI: builds the API image, boots
  the real postgres + redis + api stack, polls `/healthz`, asserts
  `/plans` exposes both tiers and `/docs` renders — deployment wiring is
  now tested, not assumed
- A PR title check enforcing Conventional Commits on pull requests
- "Data and privacy" sections in README.md and README.fa.md: self-hosted
  audio stays on the operator's machine (verified: `delete_job` unlinks
  the stored file), the browser demo uploads nothing, zero telemetry
- `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1, Persian-and-English
  friendly) and a `CODEOWNERS` file — the GitHub community profile now
  lists every recommended community health file (85% → 100%)
- A `CodeQL` workflow: weekly + per-push static security analysis of the
  Python packages (security-extended queries) and the web dashboard
- `WEBHOOK_TIMEOUT_SECONDS` and `WEBHOOK_ATTEMPTS` documented in
  `.env.example` (the Settings existed; the example file did not list
  them)

### Changed

- Branch protection on `main`: the CI (`python`/`web`/`compose`) and
  CodeQL (`Analyze *`) checks are required before a pull request merges;
  force pushes and deletions are blocked, history stays linear
- Every workflow got explicit `timeout-minutes`, a concurrency group
  where stale runs would only burn quota, and an explicit least-privilege
  `permissions` block (the Scorecard Token-Permissions check drove it)
- All GitHub Actions pinned to full commit SHAs (tag-retargeting surface
  removed) and then bumped to the latest majors — CodeQL Action v4 ahead
  of the December 2026 v3 deprecation, Node-24 actions throughout
- The Pages deploy is self-healing: stale `github-pages` artifacts are
  cleared before upload, the artifact is awaited until visible, and the
  deploy retries once past a 20 s settle gap — the transient
  "multiple artifacts / no artifacts found" failure class is gone
- `docs/ROADMAP.md` was two versions stale: v1.3 was still labelled
  "current work" and the plans feature was absent. Sections are now
  marked shipped with their versions, plans/quota are documented as a
  shipped item, and a "next — current work" section ties the open good
  first issues and the scaled fine-tune to real issue numbers
- `docs/architecture.md`: the Quota section only described the v1.3
  monthly allowance; it now documents the full plans system (free/pro
  table, both HTTP 402 codes, expiry downgrade, stacked renewals, the
  admin endpoint, and the deliberate no-payment-gateway design)
- The landing page feature grid now includes the transparent-quota card
  (free/pro limits and the honest 402 responses) — the headline feature
  of v1.4.0 was missing from the public product face
- `CITATION.cff` so the project can be cited in academic work; version
  and release date track this release
- FastAPI app metadata: MIT license info is now rendered on `/docs`
- Backend and bot package versions are dynamic now — they track
  `__version__` (single source of truth, 1.4.1 with this release)
  instead of the stale hardcoded `0.1.0` — and both carry full PEP 621
  metadata: authors, MIT license, keywords, classifiers and project URLs
- `sokhan_bot.__version__` tracks the release again (was stuck at 1.1.0)
- The web `package.json` matches the release version and declares
  description, license, repository and bugs URLs
- `deploy/docker-compose.yml` passes the plan/admin variables through to
  the containers (`PLAN_FREE_MAX_FILE_MINUTES`,
  `PLAN_PRO_MAX_FILE_MINUTES`, `PLAN_PRO_MONTHLY_MINUTES`,
  `ADMIN_API_KEY`) — before this, plan caps were not tunable and the
  admin surface answered 503 in every compose deployment
- The issue-template chooser links to Discussions for questions and
  ideas; the landing page footer does the same

## [1.4.0] - 2026-11-23

### Added

- **Plans and subscriptions** (free vs pro): every account starts on the
  **free** plan — at most a **10-minute** file and **30 minutes/month** —
  while a time-boxed **pro** subscription raises both caps to **180-minute**
  files and **1,200 minutes/month**. Both upload paths enforce the two gates
  (`POST /jobs` after the duration probe, `POST /v1/audio/transcriptions`
  after the inline decode) and answer over-limit work with HTTP 402 and a
  machine-readable `detail.code` — `file_too_long` or `quota_exceeded` — so
  every client can show a targeted upgrade message; rejected uploads are
  deleted so no storage leaks
- Plan resolution honours expiry: a pro subscription only counts while
  `plan_expires_at` is in the future, then the user silently falls back to
  free limits (`sokhan/core/plans.py`)
- **Operator grant API**: `POST /admin/users/{email}/plan` (and `GET
  /admin/users/{email}`) behind a constant-time `X-Admin-Key` check —
  grants pro for N days with renewals stacked on the remaining time, or
  reverts to free; the whole admin surface answers 503 unless
  `ADMIN_API_KEY` is set, so it can never ship accidentally open
- `GET /plans` — public plan catalogue (code, Persian/English titles, caps)
  for client upgrade screens; `GET /quota` now reports `plan`,
  `plan_expires_at` and `max_file_minutes` alongside the monthly numbers
- **Telegram bot** grew `/upgrade` (renders the plan catalogue in Persian),
  a plan-aware `/quota`, a pre-flight duration guard that refuses
  over-cap voices before downloading them, and a distinct message for the
  `file_too_long` rejection (mapping in `sokhan_bot/client.py`, tested
  against `httpx.MockTransport`)
- **Web dashboard** understands the 402 codes: the upload screen shows the
  active plan, remaining minutes and the per-file cap, and a long file
  produces the targeted "file longer than your plan allows" message (fa/en)
- Alembic migration `0004` adds `users.plan` (+ `plan_expires_at`)
- A **GitHub Pages landing page** ([site/](site/), live at
  [abolfazlrwm.github.io/sokhan](https://abolfazlrwm.github.io/sokhan/)):
  a Persian-first, RTL, dark one-pager with the measured numbers, the
  benchmark table, screenshots, the quickstart and the architecture chain —
  auto-deployed from `main` by the new `pages.yml` workflow (Pages enabled
  with `build_type: workflow`), so the shareable link never drifts from the
  repo. It ships a 1200×630 `og-image.png` for embeds with native raqm
  shaping for the Persian text
- **Coverage measurement in CI**: the test job now runs under
  `pytest-cov` with branch coverage over `sokhan` + `sokhan_bot`
  (78.2% lines / 264 of 396 branches on the non-GPU suite at the time of
  writing) and appends a per-file markdown table to the job summary via
  `scripts/coverage_summary.py`; `pytest-cov` joins the `dev` extra
- A `dependabot.yml` that keeps pip (backend, bot), npm (web),
  github-actions and docker dependencies on weekly update PRs (minor/patch
  grouped to reduce noise); majors on `next`, `typescript` and the
  python/node base images, plus `av` (its `<14` pin protects
  faster-whisper from PyAV API removals), are ignored on purpose — majors
  land as deliberate, measured upgrades. The first run's risky major PRs
  (#18, #20, #22, #26, #28) were closed with the reasoning recorded on
  each, plus a pull-request template with the measurement-first checklist

### Fixed

- The README's "honest limits" and roadmap sections still described
  streaming decode and signed webhooks as *open* roadmap items after they
  had shipped in v1.3.0; they now state the shipped facts (86.4 MB vs
  355.6 MB peak RAM on a 30-minute file, `STREAMING_DECODE` on by default,
  `callback_url` + `X-Sokhan-Signature` webhooks), and the features list
  and Docker badge were brought in sync
- `sokhan.__version__` was still `1.1.0` although v1.2.0 and v1.3.0 had
  been tagged; it now tracks the release

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
