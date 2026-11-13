# ADR 0002: Celery + Redis for the job queue

- Status: accepted
- Date: 2026-11-13

## Context

Transcription is CPU-bound and slow (minutes of compute for minutes of
audio), so HTTP requests must not run it inline. The queue needs to:

- survive worker restarts without losing jobs,
- be trivial to self-host alongside Postgres,
- support a progress callback pattern (chunks processed so far),
- work without a GPU and on modest VPS hardware.

Candidates: Celery (+Redis), arq (asyncio, Redis), RQ, or a homemade
database-polling loop.

## Decision

Use **Celery with Redis** as broker and result backend. Celery is the most
battle-tested option, documented everywhere, and its sync task model fits a
CPU-bound Whisper pipeline naturally.

Additionally the API supports `CELERY_ENABLED=false`: jobs then run inline in
a daemon thread inside the API process. That keeps the full product usable
without Redis for development and very small self-hosted deployments, and it
lets the test suite drive the pipeline without a broker.

## Consequences

- docker compose ships `api`, `worker`, `redis` and `postgres` services; the
  worker shares the backend image.
- The pipeline lives in `sokhan/worker/pipeline.py` as plain functions, so
  both the Celery task and the inline fallback call exactly the same code.
- arq/RQ stay reasonable alternatives if we ever need asyncio-native tasks;
  the enqueue boundary (`sokhan/worker/tasks.py`) isolates that choice.
