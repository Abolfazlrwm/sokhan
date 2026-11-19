#!/usr/bin/env python3
"""Publish the browser demo (space/) to the Hugging Face Space.

Used by .github/workflows/sync-space.yml on every push that touches
space/, so the live demo can never drift from main. The fine-tuned
Gradio app in space/gradio/ is deliberately excluded: HF's 2026 pricing
gates hosted Gradio/Docker Spaces behind PRO, so the public Space is the
static page and gradio/ stays self-host only.

Run locally:

    HF_TOKEN=hf_... python deploy/sync_space.py
"""

import os
import sys

from huggingface_hub import HfApi

SPACE_REPO_ID = "Abol0pati/sokhan-fa-demo"

# Files for the static page only - gradio/ is the self-hostable app.
IGNORE_PATTERNS = ["gradio/**", "gradio/*", "__pycache__/**", "*.pyc"]


def main() -> int:
    token = os.environ.get("HF_TOKEN", "")
    if not token:
        print(
            "HF_TOKEN is not set. Add it as a GitHub Actions secret "
            "(Settings / Secrets and variables / Actions) or export it locally.",
            file=sys.stderr,
        )
        return 1

    sha = os.environ.get("GITHUB_SHA", "")[:7] or "local"
    api = HfApi(token=token)
    result = api.upload_folder(
        folder_path="space",
        repo_id=SPACE_REPO_ID,
        repo_type="space",
        commit_message=f"sync from GitHub {sha}",
        ignore_patterns=IGNORE_PATTERNS,
    )
    commit_url = getattr(result, "commit_url", None)
    if commit_url:
        print(f"space synced ({sha}): {commit_url}")
    else:
        print(f"space synced ({sha}) - nothing to upload")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
