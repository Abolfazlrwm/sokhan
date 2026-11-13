# Changelog

All notable changes to Sokhan are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/) and the project versions with [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
