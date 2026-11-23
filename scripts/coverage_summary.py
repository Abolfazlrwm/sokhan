"""Render coverage.json as a markdown table for the CI job summary.

CI usage (after ``pytest --cov-report=json:coverage.json``):

    python scripts/coverage_summary.py coverage.json >> "$GITHUB_STEP_SUMMARY"

No third-party imports: runs inside the CI job without extra installs.
"""

import json
import sys


def main(path: str) -> None:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    totals = data["totals"]
    print("## Coverage")
    print()
    print(
        f"**{totals['percent_covered']:.1f}%** — "
        f"{totals['covered_lines']}/{totals['num_statements']} lines"
        + (
            f", {totals['covered_branches']}/{totals['num_branches']} branches"
            if totals.get("num_branches")
            else ""
        )
    )
    print()
    print("| File | Stmts | Miss | Cover |")
    print("| --- | ---: | ---: | ---: |")

    files = data["files"]
    for path_, info in sorted(files.items()):
        s = info["summary"]
        print(
            f"| `{path_}` | {s['num_statements']} | {s['missing_lines']} "
            f"| {s['percent_covered']:.1f}% |"
        )

    print()
    print("*Measured with branch coverage (`--cov-branch`) over "
          "`sokhan` and `sokhan_bot` on the non-GPU test suite.*")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: coverage_summary.py <coverage.json>", file=sys.stderr)
        raise SystemExit(2)
    main(sys.argv[1])
