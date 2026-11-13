"""Health, quota and archive search endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from sokhan import __version__
from sokhan.api.deps import get_current_user
from sokhan.api.serializers import job_to_out
from sokhan.config import get_settings
from sokhan.core.quota import get_quota_info
from sokhan.db import get_db
from sokhan.models import User, utcnow
from sokhan.schemas import HealthResponse, JobListResponse, QuotaResponse
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


@router.get("/quota", response_model=QuotaResponse)
def quota(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> QuotaResponse:
    settings = get_settings()
    info = get_quota_info(
        session, user.id, utcnow(), settings.free_minutes_per_user_per_month
    )
    return QuotaResponse(
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
