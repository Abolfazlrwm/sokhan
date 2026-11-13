# ADR 0001: Persian-first, open-source, self-hostable

- Status: accepted
- Date: 2026-11-13

## Context

Speech-to-text tooling overwhelmingly optimizes for English: English UIs,
English-only search, and cloud-only pricing. Persian speakers — students,
journalists, podcasters — are left with tools that mangle their language and
send their private recordings to third-party clouds.

## Decision

Sokhan treats Persian as the primary language, not a translation layer:

1. The web dashboard and the Telegram bot are written in Persian first;
   English is a secondary locale.
2. Archive search normalizes Arabic look-alike code points (ي→ی, ك→ک, ...)
   before matching, so text typed on different keyboard layouts still matches.
3. LLM summaries are prompted in Persian.
4. The whole stack is MIT-licensed and self-hostable with docker compose; no
   component requires a cloud account.

## Consequences

- Whisper (via faster-whisper) is the transcription core: it runs offline, on
  CPU, and handles Persian reasonably without any external service.
- We ship our own quota system (monthly free minutes) so a self-hosted
  instance can serve a small group without a billing provider.
- Persian-specific quality work (fine-tuning, punctuation restoration) stays
  on the roadmap instead of being delegated to a hosted API.
