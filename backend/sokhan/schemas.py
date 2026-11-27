"""Pydantic response schemas for the REST API."""

from datetime import datetime

from pydantic import BaseModel


class AuthResponse(BaseModel):
    id: str
    email: str
    api_token: str
    # Sent back as X-CSRF-Token on cookie-authenticated writes; absent for
    # flows that set no cookie (the Telegram bot).
    csrf_token: str | None = None


class SessionOut(BaseModel):
    id: str
    email: str
    csrf_token: str


class JobCreated(BaseModel):
    id: str
    status: str


class JobOut(BaseModel):
    id: str
    filename: str
    status: str
    progress: float
    duration_seconds: float
    created_at: datetime
    has_summary: bool


class SegmentOut(BaseModel):
    """One transcript span with absolute timestamps (seconds).

    `position` is a 1-based ordinal matching the SRT block numbering.
    `confidence` is the model's exp(avg_logprob) estimate in (0, 1], or null
    when the engine does not produce one.
    """

    position: int
    start: float
    end: float
    speaker: str | None = None
    confidence: float | None = None
    text: str


class JobDetailOut(JobOut):
    language: str
    want_summary: bool
    # Echoed so callers can verify which endpoint will be called back; the
    # signing secret never leaves the server (see WEBHOOK_SIGNING_SECRET).
    callback_url: str | None = None
    completed_at: datetime | None = None
    error: str | None = None
    summary: str | None = None
    text: str | None = None
    segments: list[SegmentOut] = []


class JobListResponse(BaseModel):
    items: list[JobOut]
    total: int


class QuotaResponse(BaseModel):
    plan: str
    plan_expires_at: datetime | None = None
    max_file_minutes: int
    limit_minutes: int
    used_minutes: float
    remaining_minutes: float
    month: str


class PlanOut(BaseModel):
    """One entry of the public plan catalogue (GET /plans)."""

    code: str
    title_fa: str
    title_en: str
    max_file_minutes: int
    monthly_minutes: int


class PlanListResponse(BaseModel):
    plans: list[PlanOut]


class PlanGrantRequest(BaseModel):
    plan: str  # "free" or "pro"
    days: int = 30


class PlanAssignmentOut(BaseModel):
    email: str
    plan: str
    plan_expires_at: datetime | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    whisper_model: str
    celery_enabled: bool
