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


class JobDetailOut(JobOut):
    language: str
    want_summary: bool
    completed_at: datetime | None = None
    error: str | None = None
    summary: str | None = None
    text: str | None = None


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
