"""The bot recovers when the API revokes a chat's cached token (web logout)."""

import asyncio
from types import SimpleNamespace

from sokhan_bot import texts
from sokhan_bot.client import AuthError, BackendError
from sokhan_bot.handlers import Handlers
from sokhan_bot.notify import CompletionNotifier
from sokhan_bot.store import TokenStore


class FakeClient:
    """Accepts only `valid_token`; /auth/telegram hands out `fresh-<n>`."""

    def __init__(self, valid_token: str) -> None:
        self.valid_token = valid_token
        self.registrations = 0
        self.settings = SimpleNamespace(web_base_url="http://web.test")

    def _check(self, token: str) -> None:
        if token != self.valid_token:
            raise AuthError("token rejected")

    def register_telegram(self, telegram_id: int, username: str | None) -> str:
        self.registrations += 1
        self.valid_token = f"fresh-{self.registrations}"
        return self.valid_token

    def get_quota(self, token: str) -> dict:
        self._check(token)
        return {
            "plan": "free",
            "used_minutes": 1.0,
            "limit_minutes": 30,
            "remaining_minutes": 29.0,
            "max_file_minutes": 10,
        }

    def get_job(self, token: str, job_id: str) -> dict:
        self._check(token)
        return {"status": "processing", "progress": 50.0}


class FakeMessage:
    def __init__(self, chat_id: int = 42) -> None:
        self.chat = SimpleNamespace(id=chat_id)
        self.from_user = SimpleNamespace(id=chat_id, username="sara")
        self.answers: list[str] = []

    async def answer(self, text: str, **_: object) -> None:
        self.answers.append(text)


def _handlers(tmp_path, cached_token: str, client: FakeClient) -> Handlers:
    store = TokenStore(str(tmp_path / "store.json"))
    store.set(42, cached_token)
    return Handlers(client, store)


def test_quota_re_registers_once_after_the_token_was_revoked(tmp_path):
    client = FakeClient(valid_token="current")
    handlers = _handlers(tmp_path, "revoked", client)
    message = FakeMessage()

    asyncio.run(handlers.quota(message))

    assert client.registrations == 1
    assert handlers.store.get(42) == "fresh-1"
    assert message.answers and texts.SERVER_UNREACHABLE not in message.answers


def test_a_valid_token_is_used_without_re_registering(tmp_path):
    client = FakeClient(valid_token="current")
    handlers = _handlers(tmp_path, "current", client)

    asyncio.run(handlers.quota(FakeMessage()))

    assert client.registrations == 0
    assert handlers.store.get(42) == "current"


def test_start_shows_a_working_connect_code_after_revocation(tmp_path):
    client = FakeClient(valid_token="current")
    handlers = _handlers(tmp_path, "revoked", client)
    message = FakeMessage()

    asyncio.run(handlers.start(message))

    assert "fresh-1" in message.answers[-1]
    assert "revoked" not in message.answers[-1]


def test_backend_outage_still_reports_unreachable(tmp_path):
    client = FakeClient(valid_token="current")

    def unreachable(token: str) -> dict:
        raise BackendError("down")

    client.get_quota = unreachable
    handlers = _handlers(tmp_path, "current", client)
    message = FakeMessage()

    asyncio.run(handlers.quota(message))

    assert message.answers == [texts.SERVER_UNREACHABLE]
    assert client.registrations == 0


def test_poller_untracks_and_asks_for_start_when_revoked(tmp_path):
    client = FakeClient(valid_token="current")
    store = TokenStore(str(tmp_path / "store.json"))
    store.set(42, "revoked")
    store.track("job-1", 42)
    sent: list[tuple[int, str]] = []

    notifier = CompletionNotifier(bot=None, client=client, store=store)

    async def fake_send(chat_id: int, text: str) -> bool:
        sent.append((chat_id, text))
        return True

    notifier._send = fake_send
    asyncio.run(notifier.poll_once())

    assert store.tracked() == []
    assert store.get(42) is None
    assert sent == [(42, texts.NEED_START)]
