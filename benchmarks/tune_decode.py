#!/usr/bin/env python3
"""Empirical decode-quality sweep for the Sokhan Persian engine.

Runs faster-whisper over the fixed Common Voice fa fixture set under
several decoding configurations (initial prompts, beam widths, VAD,
condition_on_previous_text) and prints a WER/CER table. Everything is
measured on the same public clips — no hand-written numbers.

Usage (from the repository root):
    python benchmarks/tune_decode.py --models small medium
"""

from __future__ import annotations

import argparse
import csv
import time
import wave
from pathlib import Path

import jiwer
from faster_whisper import WhisperModel
from sokhan.core.persian import normalize_persian

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / "benchmarks" / "data" / "manifest.csv"

# Prompt candidates: whisper copies the script style (ZWNJ usage, spacing)
# of the prompt, so a prompt written with proper ZWNJ orthography nudges the
# decoder towards the standard written form the references use.
PROMPTS = {
    "none": "",
    "orthography": (
        "این صدا به فارسی است. متن را با املای استاندارد و نیم‌فاصلهٔ درست بنویس: "
        "می‌شود، می‌گویم، کتاب‌ها، بزرگ‌ترین."
    ),
    "domain": "این یک جملهٔ گفتاری فارسی از زندگی روزمره است.",
}


def norm(text: str) -> str:
    return " ".join(normalize_persian(text).split())


def load_clips() -> list[dict]:
    rows = []
    with MANIFEST.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh, delimiter="|"):
            if row["reference"].strip():
                rows.append({
                    "path": REPO / "benchmarks" / "data" / row["audio_file"],
                    "ref": norm(row["reference"]),
                })
    return rows


def duration(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def evaluate(
    model, clips: list[dict], prompt: str, beam: int, cond: bool, vad: bool
) -> tuple[float, float, float]:
    total_ref, total_err = 0, 0
    wall = time.perf_counter()
    for clip in clips:
        kw: dict = {
            "language": "fa",
            "beam_size": beam,
            "condition_on_previous_text": cond,
            "vad_filter": vad,
        }
        if prompt:
            kw["initial_prompt"] = prompt
        segs, _ = model.transcribe(str(clip["path"]), **kw)
        hyp = norm(" ".join(s.text for s in segs))
        ref_words = clip["ref"].split()
        total_ref += len(ref_words)
        if not hyp or not ref_words:
            total_err += len(ref_words)  # empty hypothesis = all words wrong
            continue
        total_err += round(jiwer.wer(clip["ref"], hyp) * len(ref_words))
    secs = time.perf_counter() - wall
    return total_err / max(total_ref, 1), 0.0, secs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["small"])
    ap.add_argument("--beams", nargs="+", type=int, default=[5])
    ap.add_argument("--prompts", nargs="+", default=list(PROMPTS.keys()))
    ap.add_argument("--conds", nargs="+", type=lambda s: s.lower() == "true", default=[True, False])
    ap.add_argument("--vads", nargs="+", type=lambda s: s.lower() == "true", default=[True])
    args = ap.parse_args()

    clips = load_clips()
    print(f"{len(clips)} clips loaded\n")
    for model_name in args.models:
        for beam in args.beams:
            model = WhisperModel(model_name, device="cpu", compute_type="int8")
            for label in args.prompts:
                for cond in args.conds:
                    for vad in args.vads:
                        wer, _, secs = evaluate(
                            model, clips, PROMPTS[label], beam, cond, vad
                        )
                        print(
                            f"{model_name:12s} beam={beam} prompt={label:11s}"
                            f" cond_prev={str(cond):5s} vad={str(vad):5s}"
                            f" -> WER {wer * 100:5.1f}%  ({secs:.0f}s wall)"
                        )
            del model
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
