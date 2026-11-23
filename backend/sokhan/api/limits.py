"""Plan-limit enforcement shared by the job and OpenAI-compatible routes.

Both upload paths must apply the same two gates in the same order:

1. the plan's **per-file duration cap** (free = 10 min) — needs the decoded
   or probed duration, so it runs after the file is on disk; callers clean
   the stored file up on rejection
2. the plan's **monthly allowance** — pure DB arithmetic, cheap enough to
   run before the audio is even saved

Both failures surface as an honest HTTP 402 with a machine-readable
`detail.code` (`file_too_long` / `quota_exceeded`) so the web dashboard and
the Telegram bot can show a targeted upgrade message.
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from sokhan.config import get_settings
from sokhan.core.plans import Plan, plan_for_user
from sokhan.core.quota import QuotaExceededError, ensure_quota
from sokhan.models import User, utcnow


def resolve_plan(user: User) -> Plan:
    """The user's effective plan right now (expired pro falls back to free)."""
    return plan_for_user(user, get_settings(), utcnow())


def ensure_monthly_quota(session: Session, user: User, plan: Plan) -> None:
    try:
        ensure_quota(session, user.id, utcnow(), plan.monthly_minutes)
    except QuotaExceededError as exc:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code": "quota_exceeded",
                "plan": plan.code,
                "used_minutes": exc.used_minutes,
                "limit_minutes": exc.limit_minutes,
            },
        ) from exc


def ensure_file_cap(plan: Plan, duration_seconds: float | None) -> None:
    if duration_seconds is None:
        return
    minutes = duration_seconds / 60.0
    if minutes > plan.max_file_minutes:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code": "file_too_long",
                "plan": plan.code,
                "file_minutes": round(minutes, 1),
                "max_file_minutes": plan.max_file_minutes,
            },
        )
