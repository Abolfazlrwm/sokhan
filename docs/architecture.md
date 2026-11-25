# Architecture

```
                    ┌──────────────────────────────────────────────┐
                    │                  browser                     │
                    │  Next.js dashboard (fa/en, RTL-first)        │
                    └──────────────────────┬───────────────────────┘
                                           │  REST + bearer token
                                           ▼
┌──────────────┐   ┌──────────────────────────────────────────────┐
│   Telegram   ├──▶│              FastAPI (sokhan API)            │
│     bot      │   │  auth · jobs · transcripts · quota · search  │
└──────────────┘   │  POST /v1/audio/transcriptions (OpenAI-style)│
                   └──────┬───────────────────────────┬───────────┘
                          │ enqueue (Celery)          │ SQLAlchemy
                          ▼                           ▼
                   ┌──────────────┐            ┌──────────────┐
                   │ Redis broker │            │   Postgres   │
                   └──────┬───────┘            │ users · jobs │
                          │                    │ segments ·   │
                          ▼                    │ usage        │
                   ┌──────────────────────────────────────────┐  │
                   │  worker: sokhan.worker.pipeline          │  │
                   │  decode → chunk (30 s + 1 s overlap) →   │──┘
                   │  faster-whisper → merge → txt/srt/docx   │
                   │  → optional LLM summary → usage record   │
                   └──────────────────────────────────────────┘
```

## Request flow

1. **Upload** — a client (browser or bot) posts multipart audio to
   `POST /jobs`. The API checks the monthly quota, probes the duration,
   stores the file under `DATA_DIR/audio/{job_id}.{ext}` and enqueues.
2. **Process** — the worker decodes to mono 16 kHz PCM (PyAV, no external
   ffmpeg), splits into 30-second windows with a 1-second overlap,
   transcribes each window with faster-whisper, then merges the per-chunk
   segments: chunk-local timestamps become file-global, duplicate boundary
   phrases are dropped (higher-confidence variant wins), and timestamps are
   clamped to `[0, duration]`.

   By default (`STREAMING_DECODE=true`) the decode and the chunking run
   while transcription proceeds: `core/audio.py` streams block-by-block and
   `core/chunking.py::iter_chunks` emits windows from the block stream.
   Peak worker RAM tracks one 30-second window, not the file — measured on
   identical 16 kHz mono WAVs, the full decode peaks at 355.6 MB for a
   30-minute file while the streaming path stays at 86.4 MB (10-minute
   file: 169.6 MB vs 84.9 MB; ~28 MB of that is interpreter baseline).
   Diarization engines that need the whole signal (`energy`, `pyannote`
   — every engine whose `requires_full_audio` is true) automatically take
   the legacy full decode; `test_streaming.py` proves both paths produce
   identical chunks.
3. **Post-process** — when `PUNCTUATION_ENABLED` (default), each merged
   segment passes the rule-based Persian punctuation restoration
   (`core/punctuation.py`): terminal `؟` on question sentences, `.` on
   declaratives, Latin `,`/`;`/`?` mapped to their Persian counterparts and
   spacing fixed around every mark. The pass is deterministic and the WER
   benchmark path bypasses it, so measured numbers stay comparable.
4. **Persist** — merged segments (including the engine's confidence,
   exp(avg_logprob)), plain text and a search-normalized copy of the text
   (`normalize_for_search`: `normalize_persian` plus punctuation stripping)
   go to Postgres; usage seconds are appended.
5. **Consume** — clients poll `GET /jobs/{id}` for progress and fetch
   `GET /jobs/{id}/transcript?format=txt|srt|vtt|json|docx` when done.
   Segments below `LOW_CONFIDENCE_THRESHOLD` are flagged for human review
   in the exports (`⚠` prefix) and the dashboard ("needs review" badge).
   Callers that prefer push over poll pass a `callback_url` with the
   upload: when the job completes or fails, the worker POSTs a JSON event
   signed in `X-Sokhan-Signature: t=<unix>,v1=<hex hmac-sha256(secret,
   "<ts>.<body>")>` (Stripe-style; see `core/webhooks.py` and
   `WEBHOOK_SIGNING_SECRET`). Delivery is best-effort and never flips the
   job's final status.

## Storage notes

- With `STREAMING_DECODE=true` (default) the worker never holds the whole
  recording in memory — peak RAM is one 30-second window plus a block
  buffer (measured: 86.4 MB total process peak for a 30-minute file,
  versus 355.6 MB for the legacy full decode; see Request flow step 2).
  Diarization engines that need the full signal still use the one-shot
  decode.
- Uploaded audio lives on the `sokhan-data` docker volume; exports are
  generated on the fly from segments.

## Speaker diarization

Before chunking, the pipeline runs the configured `DIARIZATION_ENGINE` on the
decoded mono PCM and labels segments by temporal overlap (ADR 0003 defines the
`Diarizer` protocol, ADR 0004 the engines):

| Value | Engine | Labels |
| --- | --- | --- |
| `stub` (default) | no-op | none — speaker stays empty, exactly the v1 behaviour |
| `energy` | short-time energy VAD plus a two-cluster k-means over log-band features, numpy only | `SPK_1`/`SPK_2` — **acoustic similarity, not verified speaker identity** |
| `pyannote` | `pyannote/speaker-diarization-3.1` pipeline | model-assigned speaker identities |

Diarization is an enhancement, never a dependency: if the selected engine
cannot run (extra not installed, `PYANNOTE_HF_TOKEN` missing, model load or
inference error) the job completes without speaker labels and the reason is
logged. The pyannote engine is gated behind the optional `diarize` extra
(`pip install "backend[diarize]"`), the gated Hugging Face weights and an
operator token; the model is downloaded lazily on first use, so the default
`stub` deployment never touches it.

## Search

`text_normalized` stores `normalize_for_search(text)` (Arabic ي/ك variants
mapped to Persian ی/ک, ZWNJ and tatweel removed, punctuation marks replaced
by spaces so phrase queries match the punctuated transcripts). SQLite falls back to
`ILIKE`; Postgres adds a `pg_trgm` GIN index plus similarity scoring, created
idempotently at startup (`ensure_postgres_search_objects`).

## Quota and plans

Two plans out of the box, tuned through `PLAN_*` environment variables:

| | Free (default) | Pro |
| --- | --- | --- |
| Max file length | 10 min (`PLAN_FREE_MAX_FILE_MINUTES`) | 180 min (`PLAN_PRO_MAX_FILE_MINUTES`) |
| Monthly minutes | 30 (`FREE_MINUTES_PER_USER_PER_MONTH`) | 1200 (`PLAN_PRO_MONTHLY_MINUTES`) |

Enforcement lives in the API layer:

- The **monthly quota** is computed from the `usage_records` table (per
  user, current month). Once the total reaches the plan's allowance,
  uploads and OpenAI-compatible calls return HTTP 402 with code
  `quota_exceeded`, plus the used and remaining minutes in the body.
- The **per-file cap** is checked against the probed audio duration
  before the job is queued; over-cap files return HTTP 402 with code
  `file_too_long`.
- A **pro subscription** is a `users.plan` + `plan_expires_at` row
  (Alembic 0004). Expired subscribers fall back to the free limits
  automatically; renewals stack the remaining time on top.
- Operators grant subscriptions with `POST /admin/users/{email}/plan`
  authenticated by `X-Admin-Key` (constant-time comparison; the admin
  surface answers 503 unless `ADMIN_API_KEY` is configured). There is
  deliberately **no payment gateway** — plan changes are an operator
  decision, not a checkout.

Rejections are transparent, not silent: the dashboard and the bot
surface the same 402 codes (the bot checks a voice's length against the
caller's plan before upload and answers `/quota` with live numbers).

## Feature flags

| Flag | Default | Effect when off |
| --- | --- | --- |
| `CELERY_ENABLED` | `true` | Jobs run inline in a daemon thread; no Redis needed |
| `SUMMARY_ENABLED` | `false` | Jobs complete without a summary; no LLM calls |
| `DIARIZATION_ENGINE` | `stub` | Jobs complete without speaker labels; `energy`/`pyannote` opt in (see above) |
