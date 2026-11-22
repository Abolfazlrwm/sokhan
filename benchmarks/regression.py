"""WER regression gate for the benchmark fixture.

Deliberately free of heavy imports (no jiwer / no faster-whisper) so CI and
tests can exercise the gate logic without downloading model weights.
"""

import json
from pathlib import Path


def load_baseline(path: str | Path) -> dict[str, float]:
    """Read a baseline file ({"models": {"<name>": {"wer": ...}}}) into {name: wer}."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        name: float(entry["wer"])
        for name, entry in data.get("models", {}).items()
        if isinstance(entry, dict) and "wer" in entry
    }


def check_regression(
    runs: list[dict], baseline: dict[str, float], max_points: float
) -> list[str]:
    """Human-readable regressions for runs whose model has a recorded baseline.

    `max_points` is the tolerated WER increase in percentage points; a run
    that is better than the baseline never fails the gate.
    """
    problems: list[str] = []
    for run in runs:
        recorded = baseline.get(str(run.get("model")))
        if recorded is None:
            continue
        delta = (float(run["wer"]) - recorded) * 100  # percentage points
        if delta > max_points:
            problems.append(
                f"{run['model']}: WER {float(run['wer']) * 100:.1f}% is {delta:.1f} "
                f"points above the recorded baseline {recorded * 100:.1f}% "
                f"(allowed: +{max_points:.1f})"
            )
    return problems
