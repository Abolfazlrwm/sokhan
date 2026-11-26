"""402 code mapping and plan catalogue parsing in the backend client."""

import httpx
import pytest
from sokhan_bot.client import BackendError, FileTooLongError, QuotaError, SokhanClient
from sokhan_bot.config import BotSettings


def _client(handler) -> SokhanClient:
    settings = BotSettings(
        telegram_bot_token="t",
        api_base_url="http://api.test",
        web_base_url="http://web.test",
    )
    return SokhanClient(settings, transport=httpx.MockTransport(handler))


def test_upload_402_quota_exceeded():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            402,
            json={"detail": {"code": "quota_exceeded", "used_minutes": 30.0, "limit_minutes": 30}},
        )

    with _client(handler) as client:
        with pytest.raises(QuotaError):
            client.upload_audio("tok", "voice.ogg", b"bytes")


def test_upload_402_file_too_long():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            402,
            json={
                "detail": {
                    "code": "file_too_long",
                    "plan": "free",
                    "file_minutes": 14.2,
                    "max_file_minutes": 10,
                }
            },
        )

    with _client(handler) as client:
        with pytest.raises(FileTooLongError) as excinfo:
            client.upload_audio("tok", "voice.ogg", b"bytes")
    assert excinfo.value.max_file_minutes == 10
    assert excinfo.value.file_minutes == pytest.approx(14.2)


def test_upload_other_failure_is_plain_backend_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    with _client(handler) as client:
        with pytest.raises(BackendError) as excinfo:
            client.upload_audio("tok", "voice.ogg", b"bytes")
    assert not isinstance(excinfo.value, QuotaError)
    assert not isinstance(excinfo.value, FileTooLongError)


def test_get_plans_parses_catalogue():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/plans"
        return httpx.Response(
            200,
            json={
                "plans": [
                    {
                        "code": "free",
                        "title_fa": "رایگان",
                        "title_en": "Free",
                        "max_file_minutes": 10,
                        "monthly_minutes": 30,
                    },
                    {
                        "code": "pro",
                        "title_fa": "حرفه‌ای",
                        "title_en": "Pro",
                        "max_file_minutes": 180,
                        "monthly_minutes": 1200,
                    },
                ]
            },
        )

    with _client(handler) as client:
        plans = client.get_plans()
    assert [plan["code"] for plan in plans] == ["free", "pro"]
    assert plans[1]["max_file_minutes"] == 180


def test_register_telegram_sends_the_bot_secret():
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["secret"] = request.headers.get("X-Bot-Secret")
        return httpx.Response(200, json={"id": "u1", "email": "tg", "api_token": "tok"})

    settings = BotSettings(
        telegram_bot_token="t",
        api_base_url="http://api.test",
        web_base_url="http://web.test",
        bot_api_secret="shared",
    )
    with SokhanClient(settings, transport=httpx.MockTransport(handler)) as client:
        assert client.register_telegram(42, None) == "tok"
    assert seen["secret"] == "shared"
