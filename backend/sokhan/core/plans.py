"""Subscription plans and per-user limit resolution.

Two plans ship by default and both are operator-tunable through Settings:

- **free** — every new account. Files are capped at 10 minutes and the
  monthly allowance is small on purpose: the product must stay honest about
  what costs money to run.
- **pro** — a time-boxed subscription (granted by the operator, see
  `routes_admin.py`) that raises both caps: longer single recordings and a
  much larger monthly allowance.

A pro subscription is only honoured while `User.plan_expires_at` is in the
future; once it lapses the user silently falls back to the free limits, so
expired subscribers can never keep uploading long files.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sokhan.config import Settings
from sokhan.models import User

FREE = "free"
PRO = "pro"
PLAN_CODES = (FREE, PRO)


def as_aware(moment: datetime | None) -> datetime | None:
    """SQLite (and some drivers) hand back naive datetimes; assume UTC."""
    if moment is not None and moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment


@dataclass(frozen=True)
class Plan:
    """One subscription tier with its hard limits."""

    code: str
    title_fa: str
    title_en: str
    max_file_minutes: int
    monthly_minutes: int


def free_plan(settings: Settings) -> Plan:
    return Plan(
        code=FREE,
        title_fa="رایگان",
        title_en="Free",
        max_file_minutes=settings.plan_free_max_file_minutes,
        monthly_minutes=settings.free_minutes_per_user_per_month,
    )


def pro_plan(settings: Settings) -> Plan:
    return Plan(
        code=PRO,
        title_fa="حرفه‌ای",
        title_en="Pro",
        max_file_minutes=settings.plan_pro_max_file_minutes,
        monthly_minutes=settings.plan_pro_monthly_minutes,
    )


def plan_for_user(user: User, settings: Settings, now: datetime) -> Plan:
    """Resolve the effective plan of a user at moment `now`.

    A stored "pro" only counts while the subscription is unexpired — an
    expired subscriber gets the free limits again (and the /quota endpoint
    reports it honestly instead of showing stale pro numbers).
    """
    expires_at = as_aware(user.plan_expires_at)
    if user.plan == PRO and expires_at is not None and expires_at > now:
        return pro_plan(settings)
    return free_plan(settings)


def active_plans(settings: Settings) -> list[Plan]:
    """The public plan catalogue, in upgrade order (free first)."""
    return [free_plan(settings), pro_plan(settings)]
