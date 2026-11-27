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

    def track(
        self,
        job_id: str,
        chat_id: int,
        message_id: int | None = None,
        progress: float | None = None,
        status: str | None = None,
    ) -> None:
        """Watch a job so the notifier can push its transcript when it finishes.

        `message_id` is the Telegram progress message the notifier keeps
        editing while the job runs; watches recorded by older bot versions
        have none and simply get no live progress.
        """
        entry: dict = {"chat": chat_id, "since": time.time()}
        if message_id is not None:
            entry["message_id"] = int(message_id)
        if progress is not None:
            entry["progress"] = float(progress)
        if status is not None:
            entry["status"] = str(status)
        with self._lock:
            self._tracked[str(job_id)] = entry
            self._save()

    def watch(self, job_id: str) -> dict | None:
        """A copy of the full watch entry (chat, since, message_id, ...) or None."""
        with self._lock:
            entry = self._tracked.get(str(job_id))
            return dict(entry) if entry else None

    def set_progress(self, job_id: str, progress: float, status: str) -> None:
        """Remember the last progress reported for a job (dedupes live edits)."""
        with self._lock:
            entry = self._tracked.get(str(job_id))
            if entry is None:
                return
            entry["progress"] = float(progress)
            entry["status"] = str(status)
            self._save()

    def drop_message_id(self, job_id: str) -> None:
        """Stop editing a job's progress message (e.g. the user deleted it)."""
        with self._lock:
            entry = self._tracked.get(str(job_id))
            if entry is not None and entry.pop("message_id", None) is not None:
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
