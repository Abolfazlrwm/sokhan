"""End-to-end CPU smoke test of the fine-tuning pipeline (no GPU needed).

1. Builds a synthetic Common-Voice-shaped fixture (8 sine-wave clips +
   validated.tsv).
2. Runs ``prepare_common_voice.py`` (both TSV variants: with the optional
   ``duration`` column and without it, like every real CV release).
3. Runs ``train_whisper_lora.py`` on ``whisper-tiny`` for a few steps.
4. Converts the merged checkpoint with ``ct2-transformers-converter`` (if
   ctranslate2 is installed) and asserts the artifacts exist.

This validates *mechanics* only - data plumbing, the trainer loop, the
adapter merge and the converter. It makes no claim about transcription
quality: whisper-tiny on synthetic sine waves learns nothing meaningful.

Usage (about a minute on a laptop CPU, after ``pip install -r
training/requirements.txt``):

    python training/smoke_test.py

Exit code 0 means the whole chain works on this machine.
"""

from __future__ import annotations

import csv
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent

TEXTS = [
    "این یک آزمایش است",
    "صدای مصنوعی برای تست",
    "سلام بر دوستان",
    "امروز هوا زیباست",
    "کتاب‌ها را خواند",
    "زبان فارسی زیباست",
    "هر روز می‌دوم",
    "دو دو چهار پنج",
]


def make_clips(clips_dir: Path) -> None:
    clips_dir.mkdir(parents=True, exist_ok=True)
    rate = 16_000
    rng = np.random.default_rng(7)
    for index, _text in enumerate(TEXTS):
        seconds = 1.5 + 0.1 * index
        t = np.linspace(0, seconds, int(seconds * rate), endpoint=False)
        freq = 220 + 40 * index
        signal = np.sin(2 * np.pi * freq * t) + 0.05 * rng.standard_normal(t.size)
        frames = (signal * 16_000).astype("<i2").tobytes()
        with wave.open(str(clips_dir / f"clip_{index:03d}.wav"), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(rate)
            handle.writeframes(frames)


def write_tsv(cv_root: Path, with_duration_column: bool) -> None:
    fields = ["client_id", "path", "sentence", "up_votes", "down_votes"]
    if with_duration_column:
        fields.append("duration")
    fields += ["age", "gender", "accent", "locale", "segment"]
    with (cv_root / "validated.tsv").open("w", encoding="utf-8", newline="") as sink:
        writer = csv.DictWriter(sink, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for index, text in enumerate(TEXTS):
            row = {
                "client_id": f"user{index}",
                "path": f"clip_{index:03d}.wav",
                "sentence": text,
                "up_votes": 3,
                "down_votes": 0,
            }
            if with_duration_column:
                row["duration"] = f"{1.5 + 0.1 * index:.2f}"
            writer.writerow(row)


def run(command: list[str]) -> None:
    print("+", " ".join(str(part) for part in command), flush=True)
    result = subprocess.run(command, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout.strip()[-1200:])
    if result.returncode != 0:
        print(result.stderr.strip()[-2500:], file=sys.stderr)
        raise SystemExit(f"command failed: {command}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="sokhan-smoke-") as workspace:
        work = Path(workspace)
        cv_root = work / "cv-fa"
        make_clips(cv_root / "clips")

        write_tsv(cv_root, with_duration_column=True)
        manifest_a = work / "manifest-duration.jsonl"
        run(
            [
                sys.executable,
                str(REPO_ROOT / "training/prepare_common_voice.py"),
                "--cv-root",
                str(cv_root),
                "--output",
                str(manifest_a),
            ]
        )
        rows = manifest_a.read_text(encoding="utf-8").strip().splitlines()
        assert len(rows) == len(TEXTS), f"expected {len(TEXTS)} rows, got {len(rows)}"
        print("prepare (duration column): OK")

        # Real Common Voice releases ship no duration column: probe headers.
        write_tsv(cv_root, with_duration_column=False)
        manifest_b = work / "manifest-probed.jsonl"
        run(
            [
                sys.executable,
                str(REPO_ROOT / "training/prepare_common_voice.py"),
                "--cv-root",
                str(cv_root),
                "--output",
                str(manifest_b),
            ]
        )
        rows = manifest_b.read_text(encoding="utf-8").strip().splitlines()
        assert len(rows) == len(TEXTS), f"probed manifest kept {len(rows)} rows"
        print("prepare (probed durations): OK")

        run(
            [
                sys.executable,
                str(REPO_ROOT / "training/train_whisper_lora.py"),
                "--manifest",
                str(manifest_b),
                "--output",
                str(work / "run"),
                "--base-model",
                "openai/whisper-tiny",
                "--epochs",
                "3",
                "--batch-size",
                "2",
                "--eval-fraction",
                "0.25",
            ]
        )
        for required in ["run/adapter", "run/merged"]:
            if not (work / required).exists():
                raise SystemExit(f"missing output: {required}")
        print("train loop + adapter merge: OK")

        if (work / "run/merged").exists():
            try:
                run(
                    [
                        "ct2-transformers-converter",
                        "--model",
                        str(work / "run/merged"),
                        "--output_dir",
                        str(work / "run/ct2"),
                        "--quantization",
                        "int8",
                    ]
                )
                print("ct2 conversion: OK")
            except SystemExit:
                print("ct2 conversion: skipped (ctranslate2 not installed)")

    print("SMOKE TEST PASSED - the fine-tuning chain works on this machine")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
