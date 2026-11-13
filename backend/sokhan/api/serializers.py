"""Serialization helpers shared by the jobs and search routers."""

from sokhan.models import Job
from sokhan.schemas import JobDetailOut, JobOut


def job_to_out(job: Job) -> JobOut:
    return JobOut(
        id=job.id,
        filename=job.filename,
        status=job.status,
        progress=job.progress,
        duration_seconds=job.duration_seconds,
        created_at=job.created_at,
        has_summary=job.summary is not None,
    )


def job_to_detail(job: Job) -> JobDetailOut:
    return JobDetailOut(
        id=job.id,
        filename=job.filename,
        status=job.status,
        progress=job.progress,
        duration_seconds=job.duration_seconds,
        created_at=job.created_at,
        has_summary=job.summary is not None,
        language=job.language,
        want_summary=job.want_summary,
        completed_at=job.completed_at,
        error=job.error,
        summary=job.summary,
        text=job.text,
    )
