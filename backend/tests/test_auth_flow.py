
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


def test_telegram_register_or_login(client):
    first = client.post("/auth/telegram", json={"telegram_id": 12345, "username": "amin"})
    assert first.status_code == 200
    second = client.post("/auth/telegram", json={"telegram_id": 12345, "username": "amin"})
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


def test_jobs_require_token(client):
    response = client.get("/jobs")
    assert response.status_code == 401
