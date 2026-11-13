# ADR 0003: ship the diarization interface only (stub implementation)

- Status: accepted
- Date: 2026-11-13

## Context

Speaker diarization ("who spoke when") matters for interviews and podcasts.
The mainstream open-source path is pyannote.audio, but its models are gated
behind a Hugging Face token, weigh several hundred megabytes, pull torch into
the runtime, and require accepting additional license terms. Bundling that
into v1 would make the first self-host experience heavy and fragile for a
feature most users do not need on day one.

## Decision

Ship a `Diarizer` protocol (see `sokhan/diarization/base.py`) plus a no-op
stub. The pipeline calls the interface; segments keep `speaker=None` until a
real implementation lands. The SRT and DOCX exporters already render a
speaker prefix when one exists, so output formats will not change later.

## Consequences

- Interviews are transcribed today, without speaker labels.
- Real diarization (pyannote or a lighter alternative) is tracked in the
  repository's issue tracker and planned for the next cycle; it can arrive
  behind an environment flag without touching the pipeline contract.
- The stub logs once per worker start so operators can see it is active.
