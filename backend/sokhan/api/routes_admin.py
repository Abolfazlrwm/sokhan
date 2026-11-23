"""Operator-only endpoints: subscription grants and user plan lookups.

The whole router sits behind `require_admin` (X-Admin-Key header, constant-
time comparison; disabled unless ADMIN_API_KEY is set). This is the manual
activation path: a customer pays outside the system (card transfer, Telegram
arrangement) and the operator grants N days of the pro plan. Granting again
stacks on top of any remaining time, so renewals never truncate a live
subscription.
"""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from sokhan.api.deps import require_admin
from sokhan.core.plans import PLAN_CODES, PRO, as_aware
from sokhan.db import get_db
from sokhan.models import User, utcnow
from sokhan.schemas import PlanAssignmentOut, PlanGrantRequest

# Absolute cap on a single grant, so a typo cannot hand out a lifetime plan.
_MAX_GRANT_DAYS = 3650

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _get_user_by_email(session: Session, email: str) -> User:
    user = session.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    return user


@router.get("/users/{email}", response_model=PlanAssignmentOut)
def get_user_plan(email: str, session: Session = Depends(get_db)) -> PlanAssignmentOut:
    user = _get_user_by_email(session, email)
    return PlanAssignmentOut(
        email=user.email, plan=user.plan, plan_expires_at=user.plan_expires_at
    )


@router.post("/users/{email}/plan", response_model=PlanAssignmentOut)
def assign_plan(
    email: str,
    payload: PlanGrantRequest,
    session: Session = Depends(get_db),
) -> PlanAssignmentOut:
    if payload.plan not in PLAN_CODES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"plan must be one of: {', '.join(PLAN_CODES)}",
        )
    if payload.plan == PRO and not 1 <= payload.days <= _MAX_GRANT_DAYS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"days must be between 1 and {_MAX_GRANT_DAYS}",
        )

    user = _get_user_by_email(session, email)
    now = utcnow()
    if payload.plan == PRO:
        # Renewals stack: remaining time of a live subscription is kept and
        # the new days are appended after it.
        base = as_aware(user.plan_expires_at)
        if user.plan != PRO or base is None or base <= now:
            base = now
        user.plan = PRO
        user.plan_expires_at = base + timedelta(days=payload.days)
    else:
        user.plan = "free"
        user.plan_expires_at = None
    session.commit()
    return PlanAssignmentOut(
        email=user.email, plan=user.plan, plan_expires_at=user.plan_expires_at
    )
