"""WER benchmark for Sokhan's Persian speech-to-text engine.

Runs the faster-whisper engine over a fixed set of real Persian clips
(Mozilla Common Voice, fa, CC-0) with human-verified reference transcripts,
and reports word/character error rates after the same Persian text
normalization the product uses for search.

The point of this script is reproducibility: every number printed here comes
from a run you can repeat locally, on the same public clips. Nothing is
hand-written.

Usage (from the repository root):

    python benchmarks/benchmark_wer.py --models tiny base small

With the CI regression gate and an archived session (what the weekly
benchmark workflow runs):

    python benchmarks/benchmark_wer.py --models small \
        --baseline benchmarks/results/baseline.json --max-regression 1.0 --archive

Requirements: the backend package must be importable (``pip install -e
"backend[dev]"``), plus ``jiwer`` (in benchmarks/requirements.txt) and the
faster-whisper models themselves, which are downloaded automatically on
first use (~75 MB for tiny, ~140 MB for base, ~460 MB for small).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

import jiwer  # noqa: E402
import regression  # noqa: E402
from faster_whisper import WhisperModel  # noqa: E402
from sokhan.core.persian import normalize_persian  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent / "data"
MANIFEST = DATA_DIR / "manifest.csv"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

# Model parameter counts, straight from the Whisper paper / model cards.
MODEL_PARAMS = {
    "tiny": "39 M",
    "base": "74 M",
    "small": "244 M",
    "medium": "769 M",
    "large-v3": "1.55 B",
    # Sokhan fine-tuned checkpoints published on the Hub
    "Abol0pati/whisper-tiny-fa-sokhan": "39 M",
    "Abol0pati/whisper-small-fa-sokhan": "244 M",
}


def load_manifest() -> list[dict[str, str]]:
    """Load the (audio_file, reference) manifest shipped with the repo."""
    rows: list[dict[str, str]] = []
    with MANIFEST.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="|"):
            text = row["reference"].strip()
            if text:
                rows.append({"audio": row["audio_file"], "reference": text})
    return rows


def audio_duration(path: Path) -> float:
    """Probe the duration of a wav file without decoding it fully."""
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / handle.getframerate()


def normalize_for_wer(text: str) -> str:
    """Apply Sokhan's Persian normalizer and collapse whitespace.

    Both the reference and the hypothesis go through the exact same
    pipeline, so normalization cannot favor either side.
    """
    normalized = normalize_persian(text)
    return " ".join(normalized.split())


def run_model(model_name: str, clips: list[dict], language: str) -> dict:
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    per_clip: list[dict] = []
    wall_start = time.perf_counter()

    for clip in clips:
        path = clip["path"]
        segments, info = model.transcribe(str(path), language=language, beam_size=5)
        hypothesis = " ".join(segment.text for segment in segments).strip()
        reference = normalize_for_wer(clip["reference"])
        hypothesis_normalized = normalize_for_wer(hypothesis)

        ref_words = reference.split()
        hyp_words = hypothesis_normalized.split()
        has_hyp = bool(hyp_words)
        if ref_words:
            word_errors = jiwer.wer(reference, hypothesis_normalized) if has_hyp else 1.0
            char_errors = jiwer.cer(reference, hypothesis_normalized) if has_hyp else 1.0
        else:  # skip degenerate empty references defensively
            word_errors, char_errors = 0.0, 0.0

        per_clip.append({
            "audio": clip["audio"],
            "reference": reference,
            "hypothesis": hypothesis_normalized,
            "raw_hypothesis": hypothesis,
            "wer": round(word_errors, 4),
            "cer": round(char_errors, 4),
            "ref_words": len(ref_words),
            "hyp_words": len(hyp_words),
        })

    wall_time = time.perf_counter() - wall_start
    joined_ref = " ".join(c["reference"] for c in per_clip)
    joined_hyp = " ".join(c["hypothesis"] for c in per_clip)
    total_wer = jiwer.wer(joined_ref, joined_hyp) if joined_hyp.strip() else 1.0
    total_cer = jiwer.cer(joined_ref, joined_hyp) if joined_hyp.strip() else 1.0

    return {
        "model": model_name,
        "params": MODEL_PARAMS.get(model_name, "?"),
        "compute_type": "int8",
        "language": language,
        "clips": len(per_clip),
        "audio_seconds": round(sum(c["duration"] for c in clips), 2),
        "wall_time_seconds": round(wall_time, 2),
        "wer": round(total_wer, 4),
        "cer": round(total_cer, 4),
        "per_clip": per_clip,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models",
        nargs="+",
        default=["tiny", "base", "small"],
        help="faster-whisper model sizes to benchmark (default: tiny base small)",
    )
    parser.add_argument("--language", default="fa", help="language hint passed to the engine")
    parser.add_argument(
        "--archive",
        action="store_true",
        help="also write a timestamped copy of this session under results/archive/",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="baseline JSON; the WER gate compares runs against it",
    )
    parser.add_argument(
        "--max-regression",
        type=float,
        default=1.0,
        help="tolerated WER increase in percentage points before the gate fails (default: 1.0)",
    )
    args = parser.parse_args()

    entries = load_manifest()
    clips = []
    for entry in entries:
        path = DATA_DIR / entry["audio"]
        if not path.exists():
            print(f"missing clip: {path}", file=sys.stderr)
            continue
        clips.append({**entry, "path": path, "duration": audio_duration(path)})

    if not clips:
        print("no clips to benchmark", file=sys.stderr)
        return 1

    total_audio = sum(c["duration"] for c in clips)
    print(f"clips: {len(clips)}  |  total audio: {total_audio:.1f}s  |  language: {args.language}")

    RESULTS_DIR.mkdir(exist_ok=True)
    results = {
        "dataset": "Mozilla Common Voice (fa), clean subset, CC-0",
        "manifest": "benchmarks/data/manifest.csv",
        "normalization":
        "sokhan.core.persian.normalize_persian applied to both reference and hypothesis",
        "decoding": "beam_size=5, language hint, CPU int8",
        "total_audio_seconds": round(total_audio, 2),
        "runs": [],
    }

    for model_name in args.models:
        print(f"\n=== {model_name} ===", flush=True)
        run = run_model(model_name, clips, args.language)
        results["runs"].append(run)
        print(
            f"WER {run['wer'] * 100:.1f}%  |  CER {run['cer'] * 100:.1f}%  |  "
            f"wall {run['wall_time_seconds']}s for {run['audio_seconds']}s audio"
        )

    out_path = RESULTS_DIR / "results.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nsaved: {out_path}")

    if args.archive:
        archive_dir = RESULTS_DIR / "archive"
        archive_dir.mkdir(exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        safe_models = "-".join(name.replace("/", "_") for name in args.models)
        archive_path = archive_dir / f"{stamp}-{safe_models}.json"
        archive_path.write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"archived: {archive_path}")

    if args.baseline:
        problems = regression.check_regression(
            results["runs"], regression.load_baseline(args.baseline), args.max_regression
        )
        if problems:
            for problem in problems:
                print(f"REGRESSION: {problem}", file=sys.stderr)
            return 2
        print("regression gate passed")

    print("\n| Model | Params | WER | CER |")
    print("| --- | --- | --- | --- |")
    for run in results["runs"]:
        print(
            f"| {run['model']} | {run['params']} | {run['wer'] * 100:.1f}% "
            f"| {run['cer'] * 100:.1f}% |"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
