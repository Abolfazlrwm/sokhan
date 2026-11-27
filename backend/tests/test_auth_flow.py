import pytest

REGISTER = {"email": "amin@example.com", "password": "parool-1234"}


def test_register_returns_token(client):
    response = client.post("/auth/register", json=REGISTER)
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == REGISTER["email"]
    assert len(body["api_token"]) >= 32


def test_register_rejects_duplicates(client):
    client.post("/auth/register", json=REGISTER)
    response = client.post("/auth/register", json=REGISTER)
    assert response.status_code == 409


def test_register_rejects_short_password(client):
    response = client.post("/auth/register", json={"email": "x@example.com", "password": "short"})
    assert response.status_code == 422


def test_register_rejects_invalid_email(client):
    response = client.post("/auth/register", json={"email": "not-an-email", "password": "parool-1234"})
    assert response.status_code == 422


def test_login_roundtrip(client):
    client.post("/auth/register", json=REGISTER)
    response = client.post("/auth/login", json=REGISTER)
    assert response.status_code == 200
    assert response.json()["api_token"]


def test_login_rejects_wrong_password(client):
    client.post("/auth/register", json=REGISTER)
    response = client.post("/auth/login", json={"email": REGISTER["email"], "password": "wrong-pass"})
    assert response.status_code == 401


def test_token_login_accepts_connect_code(client):
    token = client.post("/auth/register", json=REGISTER).json()["api_token"]
    response = client.post("/auth/token-login", json={"api_token": token})
    assert response.status_code == 200
    assert response.json()["email"] == REGISTER["email"]


def test_token_login_rejects_bad_code(client):
    response = client.post("/auth/token-login", json={"api_token": "nope"})
    assert response.status_code == 401


BOT_SECRET = "bot-shared-secret"


@pytest.fixture()
def bot_secret(monkeypatch):
    from sokhan.config import get_settings

    monkeypatch.setenv("BOT_API_SECRET", BOT_SECRET)
    get_settings.cache_clear()
    yield {"X-Bot-Secret": BOT_SECRET}
    get_settings.cache_clear()


def test_telegram_register_or_login(client, bot_secret):
    body = {"telegram_id": 12345, "username": "amin"}
    first = client.post("/auth/telegram", json=body, headers=bot_secret)
    assert first.status_code == 200
    second = client.post("/auth/telegram", json=body, headers=bot_secret)
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


def test_telegram_login_rejects_callers_without_the_bot_secret(client, bot_secret):
    body = {"telegram_id": 12345}
    missing = client.post("/auth/telegram", json=body)
    wrong = client.post("/auth/telegram", json=body, headers={"X-Bot-Secret": "guess"})
    assert missing.status_code == 403
    assert wrong.status_code == 403


def test_telegram_login_is_disabled_without_a_configured_secret(client):
    response = client.post(
        "/auth/telegram", json={"telegram_id": 12345}, headers={"X-Bot-Secret": ""}
    )
    assert response.status_code == 503


def test_jobs_require_token(client):
    response = client.get("/jobs")
    assert response.status_code == 401


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_logout_revokes_the_token(client):
    token = client.post("/auth/register", json=REGISTER).json()["api_token"]
    assert client.get("/quota", headers=_bearer(token)).status_code == 200

    response = client.post("/auth/logout", headers=_bearer(token))

    assert response.status_code == 204
    assert client.get("/quota", headers=_bearer(token)).status_code == 401
    # The revoked token is no longer a valid connect code either.
    assert client.post("/auth/token-login", json={"api_token": token}).status_code == 401


def test_logout_twice_with_the_same_token_is_rejected(client):
    token = client.post("/auth/register", json=REGISTER).json()["api_token"]
    client.post("/auth/logout", headers=_bearer(token))

    assert client.post("/auth/logout", headers=_bearer(token)).status_code == 401


def test_logout_requires_a_token(client):
    assert client.post("/auth/logout").status_code == 401


def test_signing_in_after_logout_issues_a_working_token(client):
    first = client.post("/auth/register", json=REGISTER).json()["api_token"]
    client.post("/auth/logout", headers=_bearer(first))

    second = client.post("/auth/login", json=REGISTER).json()["api_token"]

    assert second != first
    assert client.get("/quota", headers=_bearer(second)).status_code == 200
