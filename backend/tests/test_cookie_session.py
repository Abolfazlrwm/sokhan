"""httpOnly cookie sessions for the dashboard, with CSRF on writes (#33)."""

import pytest
from sokhan.auth import csrf_token_for
from sokhan.config import get_settings

CREDENTIALS = {"email": "nima@example.com", "password": "parool-1234"}


@pytest.fixture()
def cookie_client(client, monkeypatch):
    """The test client speaks plain http, which never sends Secure cookies."""
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    get_settings.cache_clear()
    return client


def _sign_in(client) -> dict:
    client.post("/auth/register", json=CREDENTIALS)
    return client.post("/auth/login", json=CREDENTIALS).json()


def test_login_sets_an_httponly_session_cookie(cookie_client):
    response = cookie_client.post("/auth/register", json=CREDENTIALS)

    cookie = response.headers["set-cookie"]
    assert cookie.startswith("sokhan_session=")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    body = response.json()
    assert body["csrf_token"] == csrf_token_for(body["api_token"])


def test_cookie_is_secure_by_default(client):
    cookie = client.post("/auth/register", json=CREDENTIALS).headers["set-cookie"]
    assert "Secure" in cookie


def test_cookie_authenticates_reads_without_a_bearer_header(cookie_client):
    _sign_in(cookie_client)

    assert cookie_client.get("/quota").status_code == 200
    session = cookie_client.get("/auth/session")
    assert session.status_code == 200
    assert session.json()["email"] == CREDENTIALS["email"]


def test_cookie_writes_need_the_csrf_header(cookie_client):
    body = _sign_in(cookie_client)

    missing = cookie_client.post("/auth/logout")
    wrong = cookie_client.post("/auth/logout", headers={"X-CSRF-Token": "forged"})

    assert missing.status_code == 403
    assert wrong.status_code == 403
    # The session survived both forged attempts.
    assert cookie_client.get("/quota").status_code == 200

    ok = cookie_client.post("/auth/logout", headers={"X-CSRF-Token": body["csrf_token"]})
    assert ok.status_code == 204


def test_logout_clears_the_cookie_and_revokes_the_token(cookie_client):
    body = _sign_in(cookie_client)

    response = cookie_client.post("/auth/logout", headers={"X-CSRF-Token": body["csrf_token"]})

    assert 'sokhan_session=""' in response.headers["set-cookie"]
    assert cookie_client.get("/auth/session").status_code == 401
    bearer = {"Authorization": f"Bearer {body['api_token']}"}
    assert cookie_client.get("/quota", headers=bearer).status_code == 401


def test_bearer_clients_need_no_csrf_token(client):
    token = client.post("/auth/register", json=CREDENTIALS).json()["api_token"]
    client.cookies.clear()
    bearer = {"Authorization": f"Bearer {token}"}

    assert client.get("/auth/session", headers=bearer).status_code == 200
    assert client.post("/auth/logout", headers=bearer).status_code == 204


def test_session_without_any_credentials_is_401(client):
    assert client.get("/auth/session").status_code == 401


def test_telegram_flow_sets_no_cookie(client, monkeypatch):
    monkeypatch.setenv("BOT_API_SECRET", "s3cret")
    get_settings.cache_clear()

    response = client.post(
        "/auth/telegram", json={"telegram_id": 7}, headers={"X-Bot-Secret": "s3cret"}
    )

    assert response.status_code == 200
    assert "set-cookie" not in response.headers
    assert response.json()["csrf_token"] is None
