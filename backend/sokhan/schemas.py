"""Pydantic response schemas for the REST API."""

from datetime import datetime

from pydantic import BaseModel


class AuthResponse(BaseModel):
    id: str
    email: str
    api_token: str


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
    limit_minutes: int
    used_minutes: float
    remaining_minutes: float
    month: str


class HealthResponse(BaseModel):
    status: str
    version: str
    whisper_model: str
    celery_enabled: bool
