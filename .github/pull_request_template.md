<!--
Measurement-first: if this PR changes accuracy or performance, the numbers
in the description must come from a real run (benchmark or test), not estimates.
-->

## What and why

<!-- One or two sentences: what changes, and which issue/roadmap item it serves. -->

## Checklist

- [ ] `pytest -m "not gpu_optional"` passes locally (backend + bot)
- [ ] `ruff check backend bot training benchmarks space deploy` is clean
- [ ] `mypy --config-file backend/pyproject.toml backend/sokhan` is clean
- [ ] `web` builds if `web/` is touched (`npm run build`)
- [ ] `CHANGELOG.md` has an entry under `[Unreleased]`
- [ ] New claims carry a measurement (or a test that reproduces them)
- [ ] If `space/` changed: the `Sync demo Space` workflow will publish it automatically

## Notes for reviewers

<!-- Anything worth flagging: trade-offs, follow-ups, migration steps. -->
