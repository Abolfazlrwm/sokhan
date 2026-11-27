"""Thin httpx client for the Sokhan backend on behalf of a Telegram user."""

import httpx

from sokhan_bot.config import BotSettings


class BackendError(Exception):
    pass


class AuthError(BackendError):
    """The API rejected the token (401): revoked by a logout or a newer sign-in."""


class QuotaError(BackendError):
    """The user's monthly allowance is exhausted (402, code=quota_exceeded)."""


class FileTooLongError(BackendError):
    """The file exceeds the plan's per-file cap (402, code=file_too_long)."""

    def __init__(self, file_minutes: float, max_file_minutes: int) -> None:
        self.file_minutes = file_minutes
        self.max_file_minutes = max_file_minutes
        super().__init__(
            f"file is {file_minutes:.1f} minutes, plan allows {max_file_minutes}"
        )


class SokhanClient:
    def __init__(
        self,
        settings: BotSettings,
        timeout_seconds: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self._client = httpx.Client(timeout=timeout_seconds, transport=transport)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SokhanClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def _headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def _raise_for_auth(response: httpx.Response) -> None:
        if response.status_code == 401:
            raise AuthError("token rejected")

    def register_telegram(self, telegram_id: int, username: str | None) -> str:
        response = self._client.post(
            f"{self.settings.api_base_url}/auth/telegram",
            json={"telegram_id": telegram_id, "username": username},
            headers={"X-Bot-Secret": self.settings.bot_api_secret},
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
        self._raise_for_auth(response)
        if response.status_code == 402:
            detail = response.json().get("detail", {})
            if detail.get("code") == "file_too_long":
                raise FileTooLongError(
                    float(detail.get("file_minutes", 0.0)),
                    int(detail.get("max_file_minutes", 0)),
                )
            raise QuotaError("monthly quota exhausted")
        if response.status_code != 201:
            raise BackendError(f"upload failed with status {response.status_code}")
        return response.json()["id"]

    def get_job(self, token: str, job_id: str) -> dict:
        response = self._client.get(
            f"{self.settings.api_base_url}/jobs/{job_id}",
            headers=self._headers(token),
        )
        self._raise_for_auth(response)
        if response.status_code != 200:
            raise BackendError(f"job fetch failed with status {response.status_code}")
        return response.json()

    def get_quota(self, token: str) -> dict:
        response = self._client.get(
            f"{self.settings.api_base_url}/quota",
            headers=self._headers(token),
        )
        self._raise_for_auth(response)
        if response.status_code != 200:
            raise BackendError(f"quota fetch failed with status {response.status_code}")
        return response.json()

    def get_plans(self) -> list[dict]:
        """The public plan catalogue (no auth) for the /upgrade screen."""
        response = self._client.get(f"{self.settings.api_base_url}/plans")
        if response.status_code != 200:
            raise BackendError(f"plans fetch failed with status {response.status_code}")
        return response.json()["plans"]
