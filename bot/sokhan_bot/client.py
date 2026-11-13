"""Thin httpx client for the Sokhan backend on behalf of a Telegram user."""

import httpx

from sokhan_bot.config import BotSettings


class BackendError(Exception):
    pass


class QuotaError(BackendError):
    pass


class SokhanClient:
    def __init__(self, settings: BotSettings, timeout_seconds: float = 30.0) -> None:
        self.settings = settings
        self._client = httpx.Client(timeout=timeout_seconds)

    def close(self) -> None:
        self._client.close()

    def _headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def register_telegram(self, telegram_id: int, username: str | None) -> str:
        response = self._client.post(
            f"{self.settings.api_base_url}/auth/telegram",
            json={"telegram_id": telegram_id, "username": username},
        )
        if response.status_code != 200:
            raise BackendError(f"register failed with status {response.status_code}")
        return response.json()["api_token"]

    def upload_audio(
        self, token: str, filename: str, content: bytes, want_summary: bool = True
    ) -> str:
        response = self._client.post(
            f"{self.settings.api_base_url}/jobs",
            data={"language": "fa", "want_summary": "true" if want_summary else "false"},
            files={"file": (filename, content)},
            headers=self._headers(token),
        )
        if response.status_code == 402:
            raise QuotaError("monthly quota exhausted")
        if response.status_code != 201:
            raise BackendError(f"upload failed with status {response.status_code}")
        return response.json()["id"]

    def get_job(self, token: str, job_id: str) -> dict:
        response = self._client.get(
            f"{self.settings.api_base_url}/jobs/{job_id}",
            headers=self._headers(token),
        )
        if response.status_code != 200:
            raise BackendError(f"job fetch failed with status {response.status_code}")
        return response.json()

    def get_quota(self, token: str) -> dict:
        response = self._client.get(
            f"{self.settings.api_base_url}/quota",
            headers=self._headers(token),
        )
        if response.status_code != 200:
            raise BackendError(f"quota fetch failed with status {response.status_code}")
        return response.json()
