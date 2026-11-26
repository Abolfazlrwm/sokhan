"""Extract one version's section from CHANGELOG.md for the release notes.

Used by the Release workflow: `python scripts/extract_release_notes.py vX.Y.Z`.
The changelog is the single source of truth — a tag without a matching
section fails loudly instead of shipping empty notes.
"""
import re
import sys


def extract(text: str, version: str) -> str:
    # "## [X.Y.Z] - date" (date optional) up to the next "## ["
    pattern = rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)"
    match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    if not match:
        raise SystemExit(
            f"no CHANGELOG.md section for [{version}] — add one before tagging"
        )
    return match.group(1).strip()


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: extract_release_notes.py vX.Y.Z")
    tag = sys.argv[1]
    version = tag[1:] if tag.startswith("v") else tag
    text = open("CHANGELOG.md", encoding="utf-8").read()
    print(extract(text, version))


if __name__ == "__main__":
    main()
