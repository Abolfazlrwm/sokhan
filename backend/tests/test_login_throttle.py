import pytest
from sokhan.core.throttle import FailureThrottle

REGISTER = {"email": "amin@example.com", "password": "parool-1234"}
WRONG = {"email": REGISTER["email"], "password": "wrong-pass"}


@pytest.fixture()
def tight_login_limit(app, monkeypatch):
    from sokhan.api.routes_auth import reset_login_throttle
    from sokhan.config import get_settings

    monkeypatch.setenv("LOGIN_MAX_FAILURES", "3")
    get_settings.cache_clear()
    reset_login_throttle()


def test_login_is_throttled_after_repeated_failures(client, tight_login_limit):
    client.post("/auth/register", json=REGISTER)
    for _ in range(3):
        assert client.post("/auth/login", json=WRONG).status_code == 401

    blocked = client.post("/auth/login", json=REGISTER)
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0


def test_successful_login_clears_the_failure_count(client, tight_login_limit):
    client.post("/auth/register", json=REGISTER)
    for _ in range(2):
        client.post("/auth/login", json=WRONG)
    assert client.post("/auth/login", json=REGISTER).status_code == 200
    for _ in range(2):
        assert client.post("/auth/login", json=WRONG).status_code == 401


def test_other_accounts_are_not_locked_out(client, tight_login_limit):
    client.post("/auth/register", json=REGISTER)
    other = {"email": "sara@example.org", "password": "parool-5678"}
    client.post("/auth/register", json=other)
    for _ in range(3):
        client.post("/auth/login", json=WRONG)
    assert client.post("/auth/login", json=other).status_code == 200


def test_throttle_window_slides():
    now = [1000.0]
    throttle = FailureThrottle(max_failures=2, window_seconds=60, clock=lambda: now[0])
    throttle.record_failure("k")
    throttle.record_failure("k")
    assert throttle.retry_after("k") == 60
    now[0] += 30
    assert throttle.retry_after("k") == 30
    now[0] += 30
    assert throttle.retry_after("k") == 0
