"""Plans and subscriptions: plan resolution, per-file caps, admin grants."""

from datetime import UTC, timedelta
from pathlib import Path

import numpy as np
import pytest
from sokhan.config import get_settings
from sokhan.core.plans import plan_for_user
from sokhan.db import session_scope
from sokhan.models import Job, Usage, User, utcnow

ADMIN_KEY = "test-admin-key-123"


def _set_plan(user_id: str, plan: str, expires_at) -> None:
    with session_scope() as session:
        user = session.get(User, user_id)
        user.plan = plan
        user.plan_expires_at = expires_at


def _audio_dir() -> Path:
    return Path(get_settings().data_dir) / "audio"


def _fake_long_decode(monkeypatch) -> None:
    """Pretend the decoded audio is 700 seconds long."""
    monkeypatch.setattr(
        "sokhan.api.routes_openai.decode_to_mono_16k",
        lambda path: np.zeros(700 * 16000, dtype="float32"),
    )


@pytest.fixture()
def admin_headers(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    get_settings.cache_clear()
    yield {"X-Admin-Key": ADMIN_KEY}
    get_settings.cache_clear()


# --- plan resolution -------------------------------------------------------


def test_default_plan_is_free(app, seeded_user):
    with session_scope() as session:
        user = session.get(User, seeded_user["id"])
        resolved = plan_for_user(user, get_settings(), utcnow())
    assert resolved.code == "free"
    assert resolved.max_file_minutes == 10
    assert resolved.monthly_minutes == 30


def test_active_pro_subscription_is_honoured(app, seeded_user):
    _set_plan(seeded_user["id"], "pro", utcnow() + timedelta(days=30))
    with session_scope() as session:
        user = session.get(User, seeded_user["id"])
        resolved = plan_for_user(user, get_settings(), utcnow())
    assert resolved.code == "pro"
    assert resolved.max_file_minutes == 180
    assert resolved.monthly_minutes == 1200


def test_expired_pro_falls_back_to_free(app, seeded_user):
    _set_plan(seeded_user["id"], "pro", utcnow() - timedelta(days=1))
    with session_scope() as session:
        user = session.get(User, seeded_user["id"])
        resolved = plan_for_user(user, get_settings(), utcnow())
    assert resolved.code == "free"


# --- per-file cap on POST /jobs --------------------------------------------


def test_jobs_reject_file_over_free_cap(client, seeded_user, monkeypatch, wav_bytes):
    monkeypatch.setattr("sokhan.api.routes_jobs.probe_duration_seconds", lambda path: 700.0)

    response = client.post(
        "/jobs",
        files={"file": ("long.wav", wav_bytes, "audio/wav")},
        data={"language": "fa"},
        headers={"Authorization": f"Bearer {seeded_user['token']}"},
    )

    assert response.status_code == 402
    detail = response.json()["detail"]
    assert detail["code"] == "file_too_long"
    assert detail["plan"] == "free"
    assert detail["max_file_minutes"] == 10
    assert detail["file_minutes"] == pytest.approx(11.7, abs=0.1)
    # The stored audio must not leak on rejection and no job row survives.
    assert not any(_audio_dir().iterdir())
    with session_scope() as session:
        assert session.query(Job).count() == 0


def test_jobs_accept_long_file_for_pro(client, seeded_user, monkeypatch, wav_bytes, fake_engine):
    _set_plan(seeded_user["id"], "pro", utcnow() + timedelta(days=30))
    monkeypatch.setattr("sokhan.api.routes_jobs.probe_duration_seconds", lambda path: 700.0)

    response = client.post(
        "/jobs",
        files={"file": ("long.wav", wav_bytes, "audio/wav")},
        data={"language": "fa"},
        headers={"Authorization": f"Bearer {seeded_user['token']}"},
    )

    assert response.status_code == 201
    job_id = response.json()["id"]
    detail = client.get(
        f"/jobs/{job_id}", headers={"Authorization": f"Bearer {seeded_user['token']}"}
    ).json()
    assert detail["duration_seconds"] == pytest.approx(700.0)


def test_jobs_reject_file_over_pro_cap(client, seeded_user, monkeypatch, wav_bytes):
    _set_plan(seeded_user["id"], "pro", utcnow() + timedelta(days=30))
    monkeypatch.setattr("sokhan.api.routes_jobs.probe_duration_seconds", lambda path: 12000.0)

    response = client.post(
        "/jobs",
        files={"file": ("huge.wav", wav_bytes, "audio/wav")},
        data={"language": "fa"},
        headers={"Authorization": f"Bearer {seeded_user['token']}"},
    )

    assert response.status_code == 402
    assert response.json()["detail"]["code"] == "file_too_long"
    assert response.json()["detail"]["plan"] == "pro"
    assert response.json()["detail"]["max_file_minutes"] == 180


# --- per-file cap on the OpenAI-compatible endpoint ------------------------


def test_openai_rejects_file_over_free_cap(client, seeded_user, monkeypatch, wav_bytes):
    _fake_long_decode(monkeypatch)

    response = client.post(
        "/v1/audio/transcriptions",
        files={"file": ("long.wav", wav_bytes, "audio/wav")},
        data={"language": "fa"},
        headers={"Authorization": f"Bearer {seeded_user['token']}"},
    )

    assert response.status_code == 402
    detail = response.json()["detail"]
    assert detail["code"] == "file_too_long"
    assert not any(_audio_dir().iterdir())


def test_openai_accepts_long_file_for_pro(client, seeded_user, monkeypatch, wav_bytes):
    _set_plan(seeded_user["id"], "pro", utcnow() + timedelta(days=30))
    _fake_long_decode(monkeypatch)
    from sokhan.core.transcribe import FakeTranscriber

    monkeypatch.setattr("sokhan.api.routes_openai.get_transcriber", lambda: FakeTranscriber())

    response = client.post(
        "/v1/audio/transcriptions",
        files={"file": ("long.wav", wav_bytes, "audio/wav")},
        data={"language": "fa"},
        headers={"Authorization": f"Bearer {seeded_user['token']}"},
    )

    assert response.status_code == 200


# --- monthly allowance per plan ---------------------------------------------


def test_pro_monthly_allowance_enforced(client, seeded_user, wav_bytes):
    _set_plan(seeded_user["id"], "pro", utcnow() + timedelta(days=30))
    with session_scope() as session:
        session.add(Usage(user_id=seeded_user["id"], job_id=None, seconds=1200 * 60))

    response = client.post(
        "/jobs",
        files={"file": ("clip.wav", wav_bytes, "audio/wav")},
        data={"language": "fa"},
        headers={"Authorization": f"Bearer {seeded_user['token']}"},
    )

    assert response.status_code == 402
    detail = response.json()["detail"]
    assert detail["code"] == "quota_exceeded"
    assert detail["limit_minutes"] == 1200
    assert detail["plan"] == "pro"


# --- quota + catalogue endpoints --------------------------------------------


def test_quota_reports_plan_fields(client, seeded_user):
    body = client.get(
        "/quota", headers={"Authorization": f"Bearer {seeded_user['token']}"}
    ).json()
    assert body["plan"] == "free"
    assert body["max_file_minutes"] == 10
    assert body["limit_minutes"] == 30
    assert body["plan_expires_at"] is None


def test_quota_reports_pro_after_grant(client, seeded_user, admin_headers):
    client.post(
        "/admin/users/sara@example.com/plan",
        json={"plan": "pro", "days": 30},
        headers=admin_headers,
    )
    body = client.get(
        "/quota", headers={"Authorization": f"Bearer {seeded_user['token']}"}
    ).json()
    assert body["plan"] == "pro"
    assert body["max_file_minutes"] == 180
    assert body["limit_minutes"] == 1200
    assert body["plan_expires_at"] is not None


def test_plans_catalogue_is_public(client):
    response = client.get("/plans")
    assert response.status_code == 200
    plans = response.json()["plans"]
    assert [p["code"] for p in plans] == ["free", "pro"]
    assert plans[0]["max_file_minutes"] == 10
    assert plans[0]["monthly_minutes"] == 30
    assert plans[1]["max_file_minutes"] == 180
    assert plans[1]["monthly_minutes"] == 1200
    assert plans[1]["title_fa"] == "حرفه‌ای"


# --- admin surface -----------------------------------------------------------


def test_admin_disabled_without_key(client, seeded_user):
    response = client.post(
        "/admin/users/sara@example.com/plan", json={"plan": "pro", "days": 30}
    )
    assert response.status_code == 503


def test_admin_rejects_wrong_key(client, seeded_user, admin_headers):
    response = client.post(
        "/admin/users/sara@example.com/plan",
        json={"plan": "pro", "days": 30},
        headers={"X-Admin-Key": "not-the-key"},
    )
    assert response.status_code == 403


def test_admin_grants_pro_subscription(client, seeded_user, admin_headers):
    before = utcnow()
    response = client.post(
        "/admin/users/sara@example.com/plan",
        json={"plan": "pro", "days": 30},
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["plan"] == "pro"
    expires = body["plan_expires_at"]
    assert expires is not None
    # 30 days ± 2 seconds of test drift
    assert abs((utcnow() - before).total_seconds()) < 5
    with session_scope() as session:
        user = session.get(User, seeded_user["id"])
        assert user.plan == "pro"
        expires = user.plan_expires_at
        if expires.tzinfo is None:  # SQLite hands naive datetimes back
            expires = expires.replace(tzinfo=UTC)
        delta = expires - (before + timedelta(days=30))
        assert abs(delta.total_seconds()) < 5


def test_admin_renewal_stacks_on_remaining_time(client, seeded_user, admin_headers):
    client.post(
        "/admin/users/sara@example.com/plan",
        json={"plan": "pro", "days": 10},
        headers=admin_headers,
    )
    first = client.get(
        "/admin/users/sara@example.com", headers=admin_headers
    ).json()["plan_expires_at"]

    client.post(
        "/admin/users/sara@example.com/plan",
        json={"plan": "pro", "days": 20},
        headers=admin_headers,
    )
    second = client.get(
        "/admin/users/sara@example.com", headers=admin_headers
    ).json()["plan_expires_at"]

    from datetime import datetime

    gap = datetime.fromisoformat(second) - datetime.fromisoformat(first)
    assert abs(gap.total_seconds() - 20 * 86400) < 5


def test_admin_downgrades_to_free(client, seeded_user, admin_headers):
    client.post(
        "/admin/users/sara@example.com/plan",
        json={"plan": "pro", "days": 30},
        headers=admin_headers,
    )
    response = client.post(
        "/admin/users/sara@example.com/plan",
        json={"plan": "free"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["plan"] == "free"
    assert body["plan_expires_at"] is None
    with session_scope() as session:
        user = session.get(User, seeded_user["id"])
        assert user.plan == "free"
        assert user.plan_expires_at is None


def test_admin_rejects_invalid_payloads(client, seeded_user, admin_headers):
    assert (
        client.post(
            "/admin/users/sara@example.com/plan",
            json={"plan": "gold", "days": 30},
            headers=admin_headers,
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/admin/users/sara@example.com/plan",
            json={"plan": "pro", "days": 0},
            headers=admin_headers,
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/admin/users/nobody@example.com/plan",
            json={"plan": "pro", "days": 30},
            headers=admin_headers,
        ).status_code
        == 404
    )
