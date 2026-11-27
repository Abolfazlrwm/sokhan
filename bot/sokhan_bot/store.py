"""On-disk store mapping chat ids to API tokens, plus tracked jobs (JSON)."""

import json
import os
import threading
import time


class TokenStore:
    """Chat tokens and job watches, persisted atomically to one JSON file.

    File format (pretty-printed here for readability)::

        {
          "tokens": {"<chat_id>": "<api_token>"},
          "tracked": {"<job_id>": {"chat": 42, "since": 1699999999.0}}
        }

    Legacy files (chat_id -> token, the v1.0 format) are migrated on load.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._tokens: dict[str, str] = {}
        self._tracked: dict[str, dict] = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                loaded = json.load(handle)
            if "tokens" in loaded:
                self._tokens = loaded["tokens"]
                self._tracked = loaded.get("tracked", {})
            else:
                self._tokens = loaded

    def get(self, chat_id: int) -> str | None:
        with self._lock:
            return self._tokens.get(str(chat_id))

    def set(self, chat_id: int, token: str) -> None:
        with self._lock:
            self._tokens[str(chat_id)] = token
            self._save()

    def forget(self, chat_id: int) -> None:
        """Drop a chat's token, e.g. after the API revoked it."""
        with self._lock:
            if self._tokens.pop(str(chat_id), None) is not None:
                self._save()

    def track(self, job_id: str, chat_id: int) -> None:
        """Watch a job so the notifier can push its transcript when it finishes."""
        with self._lock:
            self._tracked[str(job_id)] = {"chat": chat_id, "since": time.time()}
            self._save()

    def untrack(self, job_id: str) -> None:
        with self._lock:
            self._tracked.pop(str(job_id), None)
            self._save()

    def tracked(self) -> list[tuple[str, int, float]]:
        """All watched jobs as (job_id, chat_id, watched_at) tuples."""
        with self._lock:
            return [
                (job_id, int(entry["chat"]), float(entry["since"]))
                for job_id, entry in self._tracked.items()
            ]

    def _save(self) -> None:
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp_path = f"{self.path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump({"tokens": self._tokens, "tracked": self._tracked}, handle)
        os.replace(tmp_path, self.path)
