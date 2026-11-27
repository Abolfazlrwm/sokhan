"""Signed job-completion webhooks.

Covers the signature scheme (roundtrip, tampering, replay, malformed
headers), delivery with retries, and the end-to-end path: a job uploaded
with a callback_url must produce a signed `job.completed` (or
`job.failed`) POST after the pipeline commits — and a dead endpoint must
never flip the job itself.
"""

import hashlib
import hmac
import json
import os
import sys
import time

import pytest

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from sokhan.core import webhooks  # noqa: E402
from sokhan.core.webhooks import (  # noqa: E402
    deliver,
    signature_headers,
    verify_signature,
)

SECRET = "wh-test-secret"
BODY = b'{"event": "job.completed", "job_id": "abc"}'


def _upload(client, headers, wav_bytes, **fields):
    data = {"language": "fa"}
    data.update(fields)
    return client.post(
        "/jobs",
        files={"file": ("callback.wav", wav_bytes, "audio/wav")},
        data=data,
        headers=headers,
    )


# --- signature scheme -------------------------------------------------------


def test_signature_roundtrip():
    headers = signature_headers(SECRET, BODY)
    stamp = headers["X-Sokhan-Timestamp"]
    assert headers["X-Sokhan-Signature"].startswith(f"t={stamp},v1=")
    assert verify_signature(
        SECRET,
        BODY,
        headers["X-Sokhan-Signature"],
        stamp,
    )


def test_signature_detects_tampering():
    headers = signature_headers(SECRET, BODY)
    tampered = BODY + b" "
    assert not verify_signature(
        SECRET,
        tampered,
        headers["X-Sokhan-Signature"],
        headers["X-Sokhan-Timestamp"],
    )


def test_signature_rejects_stale_timestamp():
    headers = signature_headers(SECRET, BODY, timestamp=int(time.time()) - 3600)
    assert not verify_signature(
        SECRET,
        BODY,
        headers["X-Sokhan-Signature"],
        headers["X-Sokhan-Timestamp"],
        tolerance_seconds=300,
    )


def test_signature_rejects_wrong_secret_and_garbage():
    headers = signature_headers(SECRET, BODY)
    assert not verify_signature("other-secret", BODY, headers["X-Sokhan-Signature"], headers["X-Sokhan-Timestamp"])
    assert not verify_signature(SECRET, BODY, "v1=deadbeef", "not-a-number")
    assert not verify_signature(SECRET, BODY, "", "123")
    assert not verify_signature("", BODY, headers["X-Sokhan-Signature"], headers["X-Sokhan-Timestamp"])


def test_signature_matches_manual_hmac():
    headers = signature_headers(SECRET, BODY, timestamp=1700000000)
    expected = hmac.new(
        SECRET.encode(), b"1700000000." + BODY, hashlib.sha256
    ).hexdigest()
    assert headers["X-Sokhan-Signature"] == f"t=1700000000,v1={expected}"


# --- delivery ---------------------------------------------------------------


def test_deliver_posts_signed_body_first_try():
    calls = []

    def post(url, body, headers, timeout):
        calls.append((url, body, headers, timeout))

    assert deliver(
        "https://hooks.example/sokhan",
        BODY,
        secret=SECRET,
        attempts=2,
        backoff_seconds=0,
        post=post,
    )
    assert len(calls) == 1
    url, body, headers, timeout = calls[0]
    assert url == "https://hooks.example/sokhan"
    assert body is BODY
    assert verify_signature(SECRET, body, headers["X-Sokhan-Signature"], headers["X-Sokhan-Timestamp"])


def test_deliver_omits_signature_without_secret():
    seen = {}
    deliver("https://hooks.example/sokhan", BODY, secret="", post=lambda *a: seen.update(headers=a[2]))
    assert "X-Sokhan-Signature" not in seen


def test_deliver_retries_then_succeeds():
    attempts = []

    def flaky(url, body, headers, timeout):
        attempts.append(url)
        if len(attempts) == 1:
            raise OSError("connection refused")

    assert deliver(
        "https://hooks.example/sokhan",
        BODY,
        attempts=2,
        backoff_seconds=0,
        post=flaky,
    )
    assert len(attempts) == 2


def test_deliver_gives_up_after_attempts():
    attempts = []

    def dead(url, body, headers, timeout):
        attempts.append(url)
        raise OSError("connection refused")

    assert not deliver(
        "https://hooks.example/sokhan",
        BODY,
        attempts=2,
        backoff_seconds=0,
        post=dead,
    )
    assert len(attempts) == 2


# --- API surface ------------------------------------------------------------


def test_callback_url_validation(client, auth, wav_bytes):
    response = _upload(client, auth, wav_bytes, callback_url="ftp://not-http")
    assert response.status_code == 422
    response = _upload(client, auth, wav_bytes, callback_url="x" * 2049)
    assert response.status_code == 422


def _wait_for_callback(captured, timeout_seconds=15):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if captured:
            return captured[0]
        time.sleep(0.1)
    raise AssertionError("no webhook was delivered")


@pytest.fixture()
def webhook_capture(monkeypatch):
    """Replace the transport, keep the real signing logic."""
    captured: list = []  # dicts with url / body / headers / ok

    def fake_post(url, body, headers, timeout):
        captured.append({"url": url, "headers": dict(headers)})

    def fake_fire(payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        from sokhan.config import get_settings

        ok = deliver(
            payload["callback_url"],
            body,
            secret=get_settings().webhook_signing_secret,
            attempts=1,
            backoff_seconds=0,
            post=fake_post,
        )
        record = captured[-1] if captured else {"url": payload["callback_url"], "headers": {}}
        if not captured:
            captured.append(record)
        record["body"] = body
        record["ok"] = ok
        return ok

    monkeypatch.setattr("sokhan.worker.pipeline.fire_job_callback", fake_fire)
    return captured


@pytest.fixture()
def webhook_secret(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SIGNING_SECRET", SECRET)


def test_completed_job_fires_signed_webhook(
    webhook_secret,
    webhook_capture,
    app,
    client,
    auth,
    wav_bytes,
    wait_for_job,
    fake_engine,
):
    response = _upload(
        client, auth, wav_bytes, callback_url="https://hooks.example/sokhan"
    )
    assert response.status_code == 201
    job_id = response.json()["id"]

    detail = wait_for_job(client, auth, job_id)
    assert detail["status"] == "completed"
    assert detail["callback_url"] == "https://hooks.example/sokhan"

    delivery = _wait_for_callback(webhook_capture)
    assert delivery["ok"]
    assert delivery["url"] == "https://hooks.example/sokhan"
    payload = json.loads(delivery["body"].decode("utf-8"))
    assert payload["event"] == "job.completed"
    assert payload["job_id"] == job_id
    assert payload["status"] == "completed"
    assert payload["language"] == "fa"
    assert "سلام بر تو" in payload["text"]
    assert payload["text_truncated"] is False
    assert payload["transcript_url"].endswith(f"/jobs/{job_id}/transcript")

    headers = delivery["headers"]
    assert verify_signature(
        SECRET, delivery["body"], headers["X-Sokhan-Signature"], headers["X-Sokhan-Timestamp"]
    )
    # The event is a replay-safe envelope: a receiver can re-verify it later.
    assert verify_signature(
        SECRET,
        delivery["body"],
        headers["X-Sokhan-Signature"],
        headers["X-Sokhan-Timestamp"],
        now=int(time.time()),
    )


def test_failed_job_fires_failure_webhook(
    webhook_secret,
    webhook_capture,
    app,
    client,
    auth,
    wav_bytes,
    wait_for_job,
    monkeypatch,
):
    class ExplodingEngine:
        def transcribe(self, samples, sample_rate, language):
            raise RuntimeError("engine exploded")

    monkeypatch.setattr(
        "sokhan.worker.pipeline.get_transcriber", lambda: ExplodingEngine()
    )

    response = _upload(
        client, auth, wav_bytes, callback_url="https://hooks.example/sokhan"
    )
    assert response.status_code == 201
    job_id = response.json()["id"]

    detail = wait_for_job(client, auth, job_id)
    assert detail["status"] == "failed"
    assert detail["error"] == "engine exploded"

    delivery = _wait_for_callback(webhook_capture)
    assert delivery["ok"]
    payload = json.loads(delivery["body"].decode("utf-8"))
    assert payload["event"] == "job.failed"
    assert payload["status"] == "failed"
    assert payload["error"] == "engine exploded"


def test_job_without_callback_url_never_posts(
    webhook_secret,
    webhook_capture,
    app,
    client,
    auth,
    wav_bytes,
    wait_for_job,
    fake_engine,
):
    response = _upload(client, auth, wav_bytes)
    assert response.status_code == 201
    detail = wait_for_job(client, auth, response.json()["id"])
    assert detail["status"] == "completed"
    assert detail["callback_url"] is None
    assert webhook_capture == []


def test_dead_endpoint_does_not_fail_the_job(
    webhook_secret,
    app,
    client,
    auth,
    wav_bytes,
    wait_for_job,
    fake_engine,
    monkeypatch,
):
    """A webhook that can never land must not flip a finished job."""

    def dead_post(url, body, headers, timeout):
        raise OSError("connection refused")

    # deliver() resolves its transport at call time through the module
    # attribute, so this one patch redirects the real callback path.
    monkeypatch.setattr(webhooks, "_default_post", dead_post)

    response = _upload(
        client, auth, wav_bytes, callback_url="https://hooks.example/sokhan"
    )
    assert response.status_code == 201
    detail = wait_for_job(client, auth, response.json()["id"])
    assert detail["status"] == "completed"
    assert "سلام بر تو" in detail["text"]


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:6379/",
        "http://localhost:8000/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/hook",
        "http://[::1]/hook",
        "http://[::ffff:192.168.1.1]/hook",
        "https://",
    ],
)
def test_callback_url_to_private_targets_is_rejected(client, auth, wav_bytes, url):
    response = _upload(client, auth, wav_bytes, callback_url=url)
    assert response.status_code == 422


def test_private_callback_url_allowed_when_opted_in(
    client, auth, wav_bytes, monkeypatch, fake_engine, wait_for_job
):
    from sokhan.config import get_settings
    from sokhan.core import webhooks

    monkeypatch.setenv("WEBHOOK_ALLOW_PRIVATE_TARGETS", "true")
    get_settings.cache_clear()
    delivered: list[str] = []
    monkeypatch.setattr(webhooks, "_default_post", lambda url, *rest: delivered.append(url))

    response = _upload(client, auth, wav_bytes, callback_url="http://10.0.0.5/hook")
    assert response.status_code == 201
    wait_for_job(client, auth, response.json()["id"])
    get_settings.cache_clear()
    assert delivered == ["http://10.0.0.5/hook"]


def test_delivery_refuses_hosts_that_resolve_privately(monkeypatch):
    import socket
    import urllib.error

    from sokhan.core import webhooks

    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]

    monkeypatch.setattr(webhooks.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(urllib.error.URLError) as caught:
        webhooks._default_post("http://hooks.example/sokhan", b"{}", {}, 1.0)
    assert isinstance(caught.value.reason, webhooks.BlockedTargetError)
