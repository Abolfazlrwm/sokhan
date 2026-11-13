"""Simple on-disk store mapping chat ids to API tokens (JSON, no dependencies)."""

import json
import os
import threading


class TokenStore:
    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._data: dict[str, str] = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                self._data = json.load(handle)

    def get(self, chat_id: int) -> str | None:
        with self._lock:
            return self._data.get(str(chat_id))

    def set(self, chat_id: int, token: str) -> None:
        with self._lock:
            self._data[str(chat_id)] = token
            self._save()

    def _save(self) -> None:
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp_path = f"{self.path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(self._data, handle)
        os.replace(tmp_path, self.path)
