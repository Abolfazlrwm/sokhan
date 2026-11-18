# Sokhan roadmap

Versioned, measurable phases. The project rule applies to everything
below: **a claim ships only with a measurement** (WER from
`benchmarks/benchmark_wer.py` on the fixed fixture, or a test that
reproduces it). Dated entries move to `CHANGELOG.md` when they land.

## v1.3 — public face (current work)

- [x] Gradio demo app (`space/`) — A/B radio: fine-tuned checkpoint vs
      untuned baseline, Persian RTL UI, CPU int8
- [ ] Publish the Space (`Abol0pati/sokhan-fa-demo`) and link it from the
      README — notebook cell 10 does it in ~2 minutes
- [ ] Model card on both fine-tuned repos (notebook cell 10 writes it;
      `training/model_card.md` is the source of truth for numbers)
- [ ] **The scaled fine-tune.** The v1.2.0 run (500 clips) beat the
      baseline by 1.2 WER points — at the edge of the fixture's noise
      floor. The same notebook at `MAX_SAMPLES = 0` (~10 h of speech,
      ~2 h on a free T4) is the single highest-value experiment left in
      the training kit. After it: re-benchmark, update the model card,
      and publish the new checkpoint — then the 500-clip run becomes the
      ablation row.
- [ ] A bigger eval fixture (target: 200 clips, stratified by age/gender
      and accent bands) so WER deltas stop being noise-limited

## v1.4 — engine quality

- Streaming/chunked decode in the worker: today the whole file is decoded
  to memory before the 30-second window split; multi-hour recordings need
  RAM proportional to file size
- Persian punctuation restoration as a post-pass (rule-based first, LLM
  behind `SUMMARY_ENABLED` as the optional upgrade)
- Initial-prompt lexicon: pass project/domain vocab to the engine so
  names and technical terms survive
- Benchmark regression gate in CI: nightly run over the fixture, fail if
  `small` WER degrades > 1 point (guards engine/dependency upgrades)

## v1.5 — product surface

- Webhooks / notification when a job finishes (plus the Telegram bot
  notifying on completion of long files)
- Confidence-aware SRT: low-confidence segments flagged for human review
- Speaker identification on top of diarization (ADR 0003/0004 define the
  interface; pyannote is the default neural engine today)
- Docker image publish to GHCR so self-hosting skips the build step

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
