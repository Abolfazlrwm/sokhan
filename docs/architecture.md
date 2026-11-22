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
4. **Consume** — clients poll `GET /jobs/{id}` for progress and fetch
   `GET /jobs/{id}/transcript?format=txt|srt|docx` when done.

## Storage notes

- The full file is decoded to memory before chunking; a one-hour stereo
  recording needs roughly 250 MB of RAM in the worker. Chunking from a
  streaming decoder is a planned improvement.
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
| `DIARIZATION_ENGINE` | `stub` | Jobs complete without speaker labels; `energy`/`pyannote` opt in (see above) |
