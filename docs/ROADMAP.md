# Sokhan roadmap

Versioned, measurable phases. The project rule applies to everything
below: **a claim ships only with a measurement** (WER from
`benchmarks/benchmark_wer.py` on the fixed fixture, or a test that
reproduces it). Dated entries move to `CHANGELOG.md` when they land.

## v1.3 — public face (current work)

- [x] Demo app (`space/`) — RTL Persian UI, mic + file + bundled sample
      clip. Shipped in two flavors: the free **Static Space** runs Whisper
      client-side (transformers.js, ONNX q8, base/small selectable,
      nothing uploaded), and the **Gradio app** (`space/gradio/`) serves
      the fine-tuned checkpoint with the production faster-whisper config
      for self-hosting — HF's 2026 pricing gates hosted Gradio/Docker
      Spaces behind a PRO subscription, which is what made the split
      necessary (discovered live: `402 Payment Required` on
      `create_repo(sdk="gradio")`)
- [x] Space published and verified end to end: a headless browser loaded
      it, transcribed a real Common Voice (fa) clip on-device (3.5 s clip,
      5.0 s wall) — https://huggingface.co/spaces/Abol0pati/sokhan-fa-demo
- [x] Model card on the whisper-small repo (the tiny repo already had
      one): measured numbers, honest caveats, usage snippet
- [ ] **The scaled fine-tune.** The v1.2.0 run (500 clips) beat the
      baseline by 1.2 WER points — at the edge of the fixture's noise
      floor. The same notebook at `MAX_SAMPLES = 0` (~10 h of speech,
      ~2 h on a free T4) is the single highest-value experiment left in
      the training kit. After it: re-benchmark, update the model card,
      and publish the new checkpoint — then the 500-clip run becomes the
      ablation row.
- [ ] **Fine-tuned checkpoint in the browser.** Upload the merged HF
      weights (notebook cell 11; the merged folder only exists right
      after a training run), export ONNX, and point the client-side demo
      at it — the free Static Space would then demo the *fine-tuned*
      model with zero hosting cost.
- [ ] A bigger eval fixture (target: 200 clips, stratified by age/gender
      and accent bands) so WER deltas stop being noise-limited

## v1.4 — engine quality

- [x] Streaming/chunked decode in the worker: the pipeline streams PyAV
  blocks and emits the same 30-second windows from the block stream —
  measured peak RSS 86.4 MB for a 30-minute file vs 355.6 MB fully decoded
  (10-minute: 84.9 MB vs 169.6 MB), and both paths produce identical chunks
  by test. Diarization engines that need the whole signal keep the full
  decode automatically
- [x] Persian punctuation restoration as a post-pass: a deterministic,
  rule-based pass (no LLM dependency) ships behind `PUNCTUATION_ENABLED` —
  Persian `؟` on question sentences, sentence periods, spacing fixed around
  every mark, Latin `,`/`;`/`?` mapped to their Persian counterparts, with
  decimals and clock times deliberately left intact. The WER benchmark path
  is untouched, so measured numbers stay comparable. Search normalization
  (`normalize_for_search`) strips punctuation on both column and query so
  phrase matching survives the new marks. The browser demo ports the same
  rule family, so product and demo show transcripts in the same shape
- [x] Initial-prompt lexicon: `WHISPER_INITIAL_PROMPT` (plus
  `WHISPER_BEAM_SIZE`) passes a domain vocab to the decoder so names and
  technical terms survive
- [x] Benchmark regression gate: the weekly `benchmark.yml` workflow runs
  the fixture against `benchmarks/results/baseline.json` and fails if
  `small` WER degrades > 1 point (guards engine/dependency upgrades)

## v1.5 — product surface

- [x] Notify when a job finishes — the Telegram bot now pushes the
  transcript (or a failure notice) the moment the backend completes, and
  external callers get push too: `POST /jobs` accepts a `callback_url` and
  the worker delivers an HMAC-signed `job.completed` / `job.failed` event
  (Stripe-style `X-Sokhan-Signature`, replay window 5 minutes, best-effort
  delivery that never flips the job status)
- [x] Confidence-aware SRT: the engine's exp(avg_logprob) is persisted per
  segment (`segments.confidence`, Alembic 0002), exposed on the API, the
  JSON export and verbose_json, flagged with `⚠` in SRT/VTT/DOCX below
  `LOW_CONFIDENCE_THRESHOLD` and badged "needs review" in the dashboard —
  human reviewers know exactly where to re-listen
- Speaker identification on top of diarization (ADR 0003/0004 define the
  interface; pyannote is the default neural engine today)
- [x] Docker image publish to GHCR so self-hosting skips the build step:
  `docker.yml` builds `sokhan-api` (serves the API and, with the Celery
  command override, the worker) and `sokhan-web` on every push to `main`
  and every version tag

## v2.0 — direction candidates (decide by measurement, not vibes)

- Persian TTS — the mirror of STT, completing "speech" in the name
- Real-time streaming transcription (mic-in, text-out live)
- Own-voice adaptation: LoRA adapters per speaker on top of the
  Persian checkpoint
- distil-large-v3 distillation for Persian: quality of `large` at a
  CPU-servable footprint

## Release hygiene (ongoing)

- SemVer + Keep-a-Changelog; a GitHub Release per minor version
- Never bump a model version without re-running the benchmark; archived
  sessions in `benchmarks/results/` are the paper trail
- CI stays green; ruff/mypy/pytest are blocking, not advisory
- [x] Coverage is measured in CI (branch coverage over `sokhan` +
      `sokhan_bot`, per-file table in the job summary) so untested paths
      are visible instead of guessed
- [x] A GitHub Pages landing page ([site/](site/)) auto-deploys from
      `main` — the shareable, always-current product face at
      https://abolfazlrwm.github.io/sokhan/
- [x] Dependabot version updates (pip/npm/actions/docker) on a weekly
      cadence, plus a PR template that repeats the measurement-first rule
