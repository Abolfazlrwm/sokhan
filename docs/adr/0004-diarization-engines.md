# ADR 0004: Diarization engines behind a flag

Date: 2026-11-13
Status: Accepted

## Context

ADR 0003 shipped only the diarization *contract*. The month-two roadmap calls
for real speaker diarization, but the two viable paths have very different
costs:

- **pyannote.audio** produces state-of-the-art speaker labels, but needs
  `torch` (a multi-gigabyte dependency), the gated
  `pyannote/speaker-diarization-3.1` weights, and an operator-generated
  Hugging Face token. Most self-hosters will not have all three, and CI must
  not depend on them.
- A **heuristic splitter** can mark voiced regions and cluster them by
  acoustic similarity with plain numpy. It runs anywhere, but its labels
  describe acoustic similarity, not verified speaker identities.

## Decision

`DIARIZATION_ENGINE` selects one of three implementations behind the existing
`Diarizer` protocol:

| value | engine | dependencies | labels |
| --- | --- | --- | --- |
| `stub` (default) | no-op | none | none — v1 behaviour |
| `energy` | energy VAD + two-cluster k-means over log-band features | numpy only | `SPK_1`/`SPK_2` — acoustic similarity, not verified identity |
| `pyannote` | pyannote speaker-diarization pipeline | torch + pyannote.audio + HF token | model-assigned speaker identities |

Rules:

1. The pipeline treats diarization as an *enhancement*: an engine that fails
   (missing import, missing token, runtime error) never fails the job — the
   job completes without speaker labels and the reason is logged.
2. The factory falls back to the stub when `pyannote` is selected but the
   environment cannot support it (no import, no token).
3. Documentation states plainly that `energy` labels are heuristic. We do not
   market them as true speaker identification.

## Consequences

- `pip install "backend[diarize]"` adds the optional torch/pyannote extras.
- Jobs never regress: the default remains `stub`, so existing deployments see
  no change until they opt in.
- Exports (SRT, DOCX) already render `[speaker]` prefixes, so labels reach
  users without further UI work.
- A future better engine (e.g. a distilled online diarizer) only needs to
  satisfy the protocol and register itself in the factory.
