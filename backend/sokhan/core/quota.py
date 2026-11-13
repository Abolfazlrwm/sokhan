"""Monthly per-user usage accounting and quota enforcement.

Usage rows are appended when a transcription finishes; the quota is the sum
of the current calendar month. Exceeding the limit raises
`QuotaExceededError`, which the API surfaces as an honest HTTP 402.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sokhan.models import Usage


class QuotaExceededError(Exception):
    def __init__(self, used_minutes: float, limit_minutes: int) -> None:
        self.used_minutes = used_minutes
        self.limit_minutes = limit_minutes
        super().__init__(
            f"monthly quota exceeded: {used_minutes:.1f}/{limit_minutes} minutes used"
        )


@dataclass(frozen=True)
class QuotaInfo:
    limit_minutes: int
    used_minutes: float
    remaining_minutes: float
    month: str  # e.g. "2026-11"


def month_key(moment: datetime) -> str:
    return moment.strftime("%Y-%m")


def month_start(moment: datetime) -> datetime:
    return moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def used_seconds_in_month(session: Session, user_id: str, moment: datetime) -> float:
    total = session.scalar(
        select(func.coalesce(func.sum(Usage.seconds), 0.0)).where(
            Usage.user_id == user_id, Usage.created_at >= month_start(moment)
        )
    )
    return float(total or 0.0)


def get_quota_info(
    session: Session, user_id: str, moment: datetime, limit_minutes: int
) -> QuotaInfo:
    used_minutes = used_seconds_in_month(session, user_id, moment) / 60.0
    remaining = max(0.0, float(limit_minutes) - used_minutes)
    return QuotaInfo(
        limit_minutes=limit_minutes,
        used_minutes=round(used_minutes, 2),
        remaining_minutes=round(remaining, 2),
        month=month_key(moment),
    )


def ensure_quota(
    session: Session, user_id: str, moment: datetime, limit_minutes: int
) -> QuotaInfo:
    """Return current quota info or raise QuotaExceededError."""
    info = get_quota_info(session, user_id, moment, limit_minutes)
    if info.used_minutes >= limit_minutes:
        raise QuotaExceededError(info.used_minutes, limit_minutes)
    return info


def record_usage(session: Session, user_id: str, job_id: str | None, seconds: float) -> None:
    """Append a usage record. The caller is responsible for committing."""
    session.add(Usage(user_id=user_id, job_id=job_id, seconds=max(0.0, float(seconds))))
