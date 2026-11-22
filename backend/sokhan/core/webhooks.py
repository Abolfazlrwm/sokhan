"""Signed job-completion webhooks.

A job can carry a `callback_url` (set at upload time). When the job leaves
the pipeline — completed or failed — the worker POSTs a small JSON event to
that URL so external callers (n8n, Zapier, an app backend, a shell script)
learn the transcript is ready without polling.

The request is authenticated the Stripe way: the body is hashed with
HMAC-SHA256 over `"<unix_timestamp>.<body>"` using `WEBHOOK_SIGNING_SECRET`,
and both parts travel in the `X-Sokhan-Signature: t=<ts>,v1=<hex>` header.
Receivers recompute the hash, compare with `hmac.compare_digest` and reject
anything older than five minutes, which blocks replay and tampering.

Delivery is best-effort by design: a dead callback endpoint must never flip
a finished transcription into a failed job. Failures are logged, retried
once and then dropped.

The decision logic lives in module-level functions with an injectable
transport so tests need no network.
"""

import hashlib
import hmac
import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from sokhan.config import get_settings

logger = logging.getLogger(__name__)

SIGNATURE_TOLERANCE_SECONDS = 300  # replay window for verification
TEXT_EXCERPT_CHARS = 4000  # full transcripts stay behind transcript_url

Poster = Callable[[str, bytes, dict[str, str], float], None]


def signature_headers(secret: str, body: bytes, timestamp: int | None = None) -> dict[str, str]:
    """Build the `X-Sokhan-*` auth headers for a webhook body."""
    if timestamp is None:
        timestamp = int(time.time())
    stamp = str(timestamp)
    mac = hmac.new(secret.encode(), f"{stamp}.".encode() + body, hashlib.sha256)
    return {
        "X-Sokhan-Timestamp": stamp,
        "X-Sokhan-Signature": f"t={stamp},v1={mac.hexdigest()}",
    }


def verify_signature(
    secret: str,
    body: bytes,
    signature: str,
    timestamp: str,
    tolerance_seconds: int = SIGNATURE_TOLERANCE_SECONDS,
    now: int | None = None,
) -> bool:
    """Check a `t=<ts>,v1=<hex>` signature against a body.

    Returns False for stale timestamps, malformed headers, unknown secrets
    and any body mutation — receivers should drop the event in all cases.
    """
    if not secret or not signature or not timestamp:
        return False
    try:
        stamp = int(timestamp)
    except ValueError:
        return False
    current = int(time.time()) if now is None else now
    if abs(current - stamp) > tolerance_seconds:
        return False
    # Parse the compact `t=<ts>,v1=<hex>` form (and accept a bare `v1=<hex>`).
    fields: dict[str, str] = {}
    for part in signature.strip().split(","):
        if "=" in part:
            key, value = part.split("=", 1)
            fields[key.strip()] = value.strip()
    provided = fields.get("v1", "")
    if not provided:
        return False
    header_ts = fields.get("t")
    if header_ts is not None and header_ts != timestamp:
        return False
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return hmac.compare_digest(mac.hexdigest(), provided)


def _default_post(url: str, body: bytes, headers: dict[str, str], timeout: float) -> None:
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response.read()


def deliver(
    url: str,
    body: bytes,
    *,
    secret: str = "",
    timeout: float = 4.0,
    attempts: int = 2,
    backoff_seconds: float = 1.0,
    post: Poster | None = None,
) -> bool:
    """POST a webhook body, retrying once; return whether any attempt landed."""
    if post is None:
        # Resolved at call time so deployments (and tests) can swap the
        # transport by patching the module attribute.
        post = _default_post
    headers: dict[str, str] = {}
    if secret:
        headers.update(signature_headers(secret, body))
    for attempt in range(max(1, attempts)):
        try:
            post(url, body, headers, timeout)
            return True
        except Exception:
            logger.warning(
                "webhook to %s failed (attempt %d/%d)", url, attempt + 1, attempts
            )
            if attempt + 1 < attempts and backoff_seconds > 0:
                time.sleep(backoff_seconds)
    return False


def build_payload(
    job: Any,
    event: str,
    error: str | None = None,
    api_base_url: str | None = None,
) -> dict[str, Any]:
    """The JSON body for a job event; never includes more than an excerpt."""
    settings = get_settings()
    base = api_base_url if api_base_url is not None else settings.api_base_url
    text = job.text or ""
    return {
        "event": event,
        "job_id": job.id,
        "status": job.status,
        "language": job.language,
        "duration_seconds": job.duration_seconds,
        "text": text[:TEXT_EXCERPT_CHARS],
        "text_truncated": len(text) > TEXT_EXCERPT_CHARS,
        "transcript_url": f"{base}/jobs/{job.id}/transcript",
        "error": error,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "callback_url": job.callback_url,
    }


def fire_job_callback(payload: dict[str, Any]) -> bool:
    """Deliver a job event to its callback_url; never raises.

    Called after the job row is committed, outside the DB session: a slow
    or dead endpoint must not hold a transaction open. When no signing
    secret is configured the event is delivered unsigned and the docs tell
    receivers to prefer deployments that sign.
    """
    url = payload.get("callback_url") or ""
    if not url:
        return False
    settings = get_settings()
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    delivered = deliver(
        url,
        body,
        secret=settings.webhook_signing_secret,
        timeout=settings.webhook_timeout_seconds,
        attempts=settings.webhook_attempts,
    )
    if delivered:
        logger.info("webhook delivered for job %s", payload.get("job_id"))
    else:
        logger.warning("webhook for job %s never landed", payload.get("job_id"))
    return delivered
