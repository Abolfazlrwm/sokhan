"""The WER regression gate: pure logic, no model downloads."""

import os
import sys

BENCHMARKS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "benchmarks")
)
if BENCHMARKS_DIR not in sys.path:
    sys.path.insert(0, BENCHMARKS_DIR)

import regression  # noqa: E402


def test_no_problems_when_wer_holds_or_improves():
    runs = [{"model": "small", "wer": 0.805}, {"model": "small", "wer": 0.78}]
    baseline = {"small": 0.805}
    assert regression.check_regression(runs, baseline, max_points=1.0) == []


def test_regression_beyond_threshold_is_reported():
    runs = [{"model": "small", "wer": 0.83}]
    baseline = {"small": 0.805}
    problems = regression.check_regression(runs, baseline, max_points=1.0)
    assert len(problems) == 1
    assert "small" in problems[0]
    assert "83.0" in problems[0]


def test_regression_within_threshold_passes():
    runs = [{"model": "small", "wer": 0.81}]  # +0.5 point
    baseline = {"small": 0.805}
    assert regression.check_regression(runs, baseline, max_points=1.0) == []


def test_models_missing_from_baseline_are_ignored():
    runs = [{"model": "tiny", "wer": 1.0}]
    baseline = {"small": 0.805}
    assert regression.check_regression(runs, baseline, max_points=1.0) == []


def test_load_baseline_reads_the_committed_file():
    path = os.path.join(BENCHMARKS_DIR, "results", "baseline.json")
    baseline = regression.load_baseline(path)
    # v2 stack (orthography prompt + fa_polish on both sides); the numbers
    # must match benchmarks/results/baseline.json — regenerate that file via
    # benchmarks/benchmark_wer.py whenever the stack changes.
    assert abs(baseline["small"] - 0.75) < 1e-9
    assert abs(baseline["Abol0pati/whisper-small-fa-sokhan"] - 0.75) < 1e-9
    assert abs(baseline["medium"] - 0.5625) < 1e-9
