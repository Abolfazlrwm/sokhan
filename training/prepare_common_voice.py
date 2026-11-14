"""Prepare a Common Voice (fa) training manifest for Whisper fine-tuning.

Reads a Common Voice release directory (the layout every CV release ships:
``clips/`` plus ``validated.tsv``), filters the usable rows, and writes a
JSONL manifest consumed by ``train_whisper_lora.py``.

Usage:

    python training/prepare_common_voice.py \
        --cv-root ~/datasets/cv-corpus-XX/fa \
        --output training/data/common-voice-fa \
        --max-hours 100

Durations come from the TSV's ``duration`` column when the release ships one;
Common Voice releases do not, so the script falls back to reading audio
headers with soundfile (no full decode - fast enough for the whole corpus).
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

VALIDATED_TSV = "validated.tsv"
MIN_UPVOTES = 2  # Common Voice convention: two positive votes to trust a clip


def probe_duration(audio_path: Path) -> float:
    """Read the clip duration from the audio header (no full decode)."""
    try:
        import soundfile as sf
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise SystemExit(
            "soundfile is required to probe clip durations; "
            "pip install soundfile"
        ) from exc
    info = sf.info(str(audio_path))
    return info.frames / info.samplerate


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
            raw_duration = (row.get("duration") or "").strip()
            if raw_duration:
                try:
                    duration = float(raw_duration)
                except ValueError:
                    skipped_duration += 1
                    continue
            else:
                audio_path = args.cv_root / "clips" / (row.get("path") or "")
                if not audio_path.exists():
                    skipped_duration += 1
                    continue
                try:
                    duration = probe_duration(audio_path)
                except Exception:  # noqa: BLE001 - unreadable clip, drop the row
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
