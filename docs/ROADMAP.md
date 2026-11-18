# Sokhan roadmap

Versioned, measurable phases. The project rule applies to everything
below: **a claim ships only with a measurement** (WER from
`benchmarks/benchmark_wer.py` on the fixed fixture, or a test that
reproduces it). Dated entries move to `CHANGELOG.md` when they land.

## v1.3 — public face (current work)

- [x] Demo app (`space/`) — RTL Persian UI, mic + file + bundled sample
      clip. Shipped in two flavors: the free **Static Space** runs Whisper
      client-side (transformers.js, ONNX q8, base/small selectable,
      nothing uploaded), and the **Gradio app** (`space/gradio/`) serves
      the fine-tuned checkpoint with the production faster-whisper config
      for self-hosting — HF's 2026 pricing gates hosted Gradio/Docker
      Spaces behind a PRO subscription, which is what made the split
      necessary (discovered live: `402 Payment Required` on
      `create_repo(sdk="gradio")`)
- [x] Space published and verified end to end: a headless browser loaded
      it, transcribed a real Common Voice (fa) clip on-device (3.5 s clip,
      5.0 s wall) — https://huggingface.co/spaces/Abol0pati/sokhan-fa-demo
- [x] Model card on the whisper-small repo (the tiny repo already had
      one): measured numbers, honest caveats, usage snippet
- [ ] **The scaled fine-tune.** The v1.2.0 run (500 clips) beat the
      baseline by 1.2 WER points — at the edge of the fixture's noise
      floor. The same notebook at `MAX_SAMPLES = 0` (~10 h of speech,
      ~2 h on a free T4) is the single highest-value experiment left in
      the training kit. After it: re-benchmark, update the model card,
      and publish the new checkpoint — then the 500-clip run becomes the
      ablation row.
- [ ] **Fine-tuned checkpoint in the browser.** Upload the merged HF
      weights (notebook cell 11; the merged folder only exists right
      after a training run), export ONNX, and point the client-side demo
      at it — the free Static Space would then demo the *fine-tuned*
      model with zero hosting cost.
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
