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
3. **Persist** — merged segments, plain text and a normalized copy of the
   text (`normalize_persian`) go to Postgres; usage seconds are appended.
4. **Consume** — clients poll `GET /jobs/{id}` for progress and fetch
   `GET /jobs/{id}/transcript?format=txt|srt|docx` when done.

## Storage notes

- The full file is decoded to memory before chunking; a one-hour stereo
  recording needs roughly 250 MB of RAM in the worker. Chunking from a
  streaming decoder is a planned improvement.
- Uploaded audio lives on the `sokhan-data` docker volume; exports are
  generated on the fly from segments.

## Search

`text_normalized` stores `normalize_persian(text)` (Arabic ي/ك variants
mapped to Persian ی/ک, ZWNJ and tatweel removed). SQLite falls back to
`ILIKE`; Postgres adds a `pg_trgm` GIN index plus similarity scoring, created
idempotently at startup (`ensure_postgres_search_objects`).

## Quota

`FREE_MINUTES_PER_USER_PER_MONTH` (default 30) is enforced from the
`usage_records` table: once a user's current-month total reaches the limit,
uploads and OpenAI-compatible calls return HTTP 402 with the used and
remaining minutes in the body. Rejections are transparent, not silent.

## Feature flags

| Flag | Default | Effect when off |
| --- | --- | --- |
| `CELERY_ENABLED` | `true` | Jobs run inline in a daemon thread; no Redis needed |
| `SUMMARY_ENABLED` | `false` | Jobs complete without a summary; no LLM calls |
