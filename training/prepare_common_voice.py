"""Prepare a Common Voice (fa) training manifest for Whisper fine-tuning.

Reads a Common Voice release directory (the layout every CV release ships:
``clips/`` plus ``validated.tsv``), filters the usable rows, and writes a
JSONL manifest consumed by ``train_whisper_lora.py``.

Usage:

    python training/prepare_common_voice.py \
        --cv-root ~/datasets/cv-corpus-XX/fa \
        --output training/data/common-voice-fa \
        --max-hours 100

The script performs no transcription or audio processing of its own — it only
selects rows and measures durations from the TSV's duration column, so it is
fast enough for the full corpus.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

VALIDATED_TSV = "validated.tsv"
MIN_UPVOTES = 2  # Common Voice convention: two positive votes to trust a clip


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cv-root", type=Path, required=True, help="Common Voice fa release directory"
    )
    parser.add_argument("--output", type=Path, required=True, help="JSONL manifest output path")
    parser.add_argument("--min-seconds", type=float, default=1.0, help="drop shorter clips")
    parser.add_argument("--max-seconds", type=float, default=30.0, help="drop longer clips")
    parser.add_argument(
        "--max-hours", type=float, default=0.0, help="stop after this many hours (0 = all)"
    )
    parser.add_argument(
        "--min-text-chars", type=int, default=4, help="drop transcripts shorter than this"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tsv_path = args.cv_root / VALIDATED_TSV
    if not tsv_path.exists():
        raise SystemExit(
            f"missing {tsv_path} — point --cv-root at a Common Voice release directory"
        )

    kept = 0
    skipped_votes = skipped_duration = skipped_text = 0
    total_seconds = 0.0
    args.output.parent.mkdir(parents=True, exist_ok=True)

    with tsv_path.open(encoding="utf-8", newline="") as source, args.output.open(
        "w", encoding="utf-8"
    ) as sink:
        reader = csv.DictReader(source, delimiter="\t")
        for row in reader:
            sentence = (row.get("sentence") or "").strip()
            if len(sentence) < args.min_text_chars:
                skipped_text += 1
                continue
            up_votes = int(row.get("up_votes") or 0)
            down_votes = int(row.get("down_votes") or 0)
            if down_votes > 0 or up_votes < MIN_UPVOTES:
                skipped_votes += 1
                continue
            try:
                duration = float(row.get("duration") or 0.0)
            except ValueError:
                skipped_duration += 1
                continue
            if duration < args.min_seconds or duration > args.max_seconds:
                skipped_duration += 1
                continue
            if args.max_hours and total_seconds + duration > args.max_hours * 3600:
                break

            audio_path = args.cv_root / "clips" / (row.get("path") or "")
            record = {
                "audio": str(audio_path),
                "text": sentence,
                "duration_seconds": round(duration, 3),
            }
            sink.write(json.dumps(record, ensure_ascii=False) + "\n")
            kept += 1
            total_seconds += duration

    print(f"kept: {kept} clips ({total_seconds / 3600:.2f} h)")
    print(
        f"skipped: {skipped_votes} by votes, {skipped_duration} by duration, "
        f"{skipped_text} by text"
    )
    print(f"manifest: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
