#!/usr/bin/env python3
"""Grow the WER fixture: sample verified-transcript candidates, not vibes.

Issue #29 wants the 12-clip fixture extended to 30+ clips so WER deltas
stop being noise-limited. The fixture's whole value is that its references
are **human-verified** — so this tool does everything EXCEPT the listening:

1. streams the public CC-0 mirror the training pipeline already uses
   (`pymmdrza/Common-Voice-Speech-26.0-Persian-Clean`), from a held-out
   split (`test` / `validation`) so nothing the fine-tune trained on can
   leak into the fixture;
2. filters and samples candidates (duration band, word count, dedupe
   against the existing manifest by normalized text);
3. runs the candidate through TWO independent engines with the v3 decode
   stack (beam 5, VAD on, drift guard — the product protocol) and records
   both transcripts plus their agreement WER. Two engines agreeing is
   strong evidence the clip is clean and the text is stable; disagreement
   flags noisy clips worth skipping;
4. writes `candidates/<n>.wav` + `candidates.csv` — **it never touches
   `manifest.csv`**. Promotion is a human step: listen, fix the reference
   where needed, append the row, commit, re-run the benchmark session.

Usage (from the repository root; needs `pip install pyarrow soundfile` in
addition to the benchmark requirements):

    python benchmarks/extend_fixture.py --count 20                    # default engines
    python benchmarks/extend_fixture.py --count 3 --engines tiny base # cheap smoke run

The default engine pair (`large-v3-turbo` + `medium`) is the best-measured
pair on the current fixture (benchmarks/README.md); any faster-whisper
model id works, including Sokhan fine-tuned repos.
"""

from __future__ import annotations

import argparse
import csv
import io
import random
import sys
import time
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

import jiwer  # noqa: E402
from faster_whisper import WhisperModel  # noqa: E402
from sokhan.core.fa_polish import polish_transcript  # noqa: E402
from sokhan.core.persian import normalize_persian  # noqa: E402
from sokhan.core.transcribe import looks_like_wrong_language  # noqa: E402

MIRROR = "pymmdrza/Common-Voice-Speech-26.0-Persian-Clean"
DATA_DIR = Path(__file__).resolve().parent / "data"
MANIFEST = DATA_DIR / "manifest.csv"

# The shipped fixture spans 3.5-6.9 s; candidates use the same band so the
# fixture's per-clip statistics stay comparable.
MIN_SECONDS, MAX_SECONDS = 3.0, 8.0
MIN_WORDS, MAX_WORDS = 3, 28


def normalize_for_wer(text: str) -> str:
    """Same pipeline as benchmark_wer.py: polish -> normalize -> collapse."""
    normalized = normalize_persian(polish_transcript(text))
    return " ".join(normalized.split())


def existing_references() -> set[str]:
    """Normalized reference texts already in the fixture (dedupe guard)."""
    known: set[str] = set()
    with MANIFEST.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="|"):
            known.add(normalize_for_wer(row["reference"]))
    return known


def load_split(split: str) -> list[dict]:
    """Stream one (small, held-out) shard of the mirror into memory.

    The mirror ships one-file splits for test/validation (~70 MB each),
    which is exactly the scale a candidate-sampling pass wants; the huge
    train split is deliberately not touched here.
    """
    from huggingface_hub import hf_hub_download, list_repo_files

    files = [f for f in list_repo_files(MIRROR, repo_type="dataset")
             if f.startswith(f"data/{split}-") and f.endswith(".parquet")]
    if not files:
        raise SystemExit(f"no parquet shard for split {split!r} in {MIRROR}")
    rows: list[dict] = []
    import pyarrow.parquet as pq

    for filename in files:
        local = hf_hub_download(MIRROR, filename, repo_type="dataset")
        table = pq.read_table(local, columns=["audio", "text"])
        audios = table.column("audio").to_pylist()
        texts = table.column("text").to_pylist()
        for audio, text in zip(audios, texts, strict=False):
            rows.append({"bytes": audio.get("bytes"), "text": (text or "").strip()})
    return rows


def wav_duration(raw: bytes) -> float:
    with wave.open(io.BytesIO(raw), "rb") as handle:
        return handle.getnframes() / handle.getframerate()


def decode_with_v3(model: WhisperModel, path: Path, language: str) -> str:
    """One engine pass under the v3 protocol, mirroring benchmark_wer.py."""
    segments, _info = model.transcribe(
        str(path), language=language, beam_size=5, vad_filter=True,
    )
    hypothesis = " ".join(segment.text for segment in segments).strip()
    if looks_like_wrong_language(hypothesis, language):
        retry, _info = model.transcribe(
            str(path), language=language, beam_size=5, vad_filter=True,
            temperature=0.0, condition_on_previous_text=False,
        )
        hypothesis = " ".join(segment.text for segment in retry).strip()
    return hypothesis.strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--count", type=int, default=20, help="candidates to sample")
    ap.add_argument("--split", default="test", choices=["test", "validation"],
                    help="held-out mirror split to sample from (default: test)")
    ap.add_argument("--engines", nargs="+", default=["large-v3-turbo", "medium"],
                    help="two independent faster-whisper models for the agreement check")
    ap.add_argument("--seed", type=int, default=42, help="sampling seed (reproducible)")
    ap.add_argument("--max-agreement", type=float, default=0.25,
                    help="agreement WER below which a candidate is pre-flagged keep=yes")
    ap.add_argument("--out-dir", type=Path, default=DATA_DIR / "candidates",
                    help="where candidate wavs + candidates.csv are written")
    ap.add_argument("--language", default="fa")
    args = ap.parse_args()

    if len(args.engines) != 2:
        ap.error("--engines takes exactly two models (the agreement is pairwise)")

    known = existing_references()
    print(f"fixture references loaded: {len(known)} (dedupe against these)")

    rows = load_split(args.split)
    print(f"mirror split {args.split!r}: {len(rows)} rows")
    pool: list[dict] = []
    for row in rows:
        if not row["bytes"] or not row["text"]:
            continue
        try:
            seconds = wav_duration(row["bytes"])
        except Exception:
            continue
        if not (MIN_SECONDS <= seconds <= MAX_SECONDS):
            continue
        words = len(row["text"].split())
        if not (MIN_WORDS <= words <= MAX_WORDS):
            continue
        if normalize_for_wer(row["text"]) in known:
            continue  # same sentence already verified in the fixture
        pool.append({**row, "seconds": seconds})
    print(f"candidates in band {MIN_SECONDS}-{MAX_SECONDS}s, {MIN_WORDS}-{MAX_WORDS} words, "
          f"not already in the fixture: {len(pool)}")

    random.Random(args.seed).shuffle(pool)
    picked = pool[: args.count]
    if not picked:
        print("nothing to sample — raise the band or check the split")
        return 1

    args.out_dir.mkdir(parents=True, exist_ok=True)
    models = []
    for name in args.engines:
        print(f"loading engine {name} …")
        models.append((name, WhisperModel(name, device="cpu", compute_type="int8")))

    csv_path = args.out_dir / "candidates.csv"
    fields = ["audio", "duration_s", "mirror_text",
              "engine_a", "engine_a_text", "engine_b", "engine_b_text",
              "agreement_wer", "keep", "reference_after_listening"]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="|")
        writer.writeheader()
        kept = 0
        for i, row in enumerate(picked, 1):
            name = f"candidate_{args.split}_{i:03d}.wav"
            wav_path = args.out_dir / name
            with wav_path.open("wb") as raw:
                raw.write(row["bytes"])
            transcripts = {}
            for label, model in models:
                started = time.perf_counter()
                transcripts[label] = decode_with_v3(model, wav_path, args.language)
                print(f"  [{i}/{len(picked)}] {label}: "
                      f"{time.perf_counter() - started:.1f}s -> {transcripts[label][:60]}")
            engine_a, engine_b = args.engines
            a_norm = normalize_for_wer(transcripts[engine_a])
            b_norm = normalize_for_wer(transcripts[engine_b])
            agreement = jiwer.wer(a_norm, b_norm) if a_norm and b_norm else 1.0
            keep = "yes" if agreement <= args.max_agreement else "review"
            kept += keep == "yes"
            writer.writerow({
                "audio": f"candidates/{name}",
                "duration_s": round(row["seconds"], 2),
                "mirror_text": row["text"],
                "engine_a": engine_a,
                "engine_a_text": transcripts[engine_a],
                "engine_b": engine_b,
                "engine_b_text": transcripts[engine_b],
                "agreement_wer": round(agreement, 4),
                "keep": keep,
                "reference_after_listening": "",
            })

    print(f"\nwrote {len(picked)} candidates to {args.out_dir}")
    print(f"pre-flagged keep=yes (agreement <= {args.max_agreement:.0%}): {kept}/{len(picked)}")
    print("next — the human step this tool cannot do:\n"
          "  1. listen to each wav, confirm/correct the transcript\n"
          "  2. put the verified text in `reference_after_listening`\n"
          "  3. append those rows to benchmarks/data/manifest.csv (format: audio|reference)\n"
          "  4. delete the rejected rows, commit, and re-run the benchmark session\n"
          "     (benchmarks/README.md documents the exact procedure)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
