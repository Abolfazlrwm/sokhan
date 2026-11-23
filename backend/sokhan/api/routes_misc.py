"""Health, plans, quota and archive search endpoints."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from sokhan import __version__
from sokhan.api.deps import get_current_user
from sokhan.api.limits import resolve_plan
from sokhan.api.serializers import job_to_out
from sokhan.config import get_settings
from sokhan.core.plans import active_plans
from sokhan.core.quota import get_quota_info
from sokhan.db import get_db
from sokhan.models import User, utcnow
from sokhan.schemas import (
    HealthResponse,
    JobListResponse,
    PlanListResponse,
    PlanOut,
    QuotaResponse,
)
from sokhan.search import search_jobs

router = APIRouter(tags=["misc"])


@router.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=__version__,
        whisper_model=settings.whisper_model_size,
        celery_enabled=settings.celery_enabled,
    )


@router.get("/plans", response_model=PlanListResponse)
def plans() -> PlanListResponse:
    """The public plan catalogue — no auth, clients render upgrade screens."""
    return PlanListResponse(
        plans=[PlanOut(**asdict(plan)) for plan in active_plans(get_settings())]
    )


@router.get("/quota", response_model=QuotaResponse)
def quota(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> QuotaResponse:
    plan = resolve_plan(user)
    info = get_quota_info(session, user.id, utcnow(), plan.monthly_minutes)
    return QuotaResponse(
        plan=plan.code,
        plan_expires_at=user.plan_expires_at,
        max_file_minutes=plan.max_file_minutes,
        limit_minutes=info.limit_minutes,
        used_minutes=info.used_minutes,
        remaining_minutes=info.remaining_minutes,
        month=info.month,
    )


@router.get("/search", response_model=JobListResponse)
def search(
    q: str = Query("", max_length=200),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> JobListResponse:
    jobs = search_jobs(session, user.id, q)
    return JobListResponse(items=[job_to_out(job) for job in jobs], total=len(jobs))
