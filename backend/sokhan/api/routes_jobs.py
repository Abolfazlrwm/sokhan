"""Job lifecycle: upload, status, transcripts, summary and delete."""

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sokhan.api.deps import get_current_user
from sokhan.api.serializers import job_to_detail, job_to_out
from sokhan.config import get_settings
from sokhan.core.audio import delete_audio, probe_duration_seconds, save_upload
from sokhan.core.formats import to_docx, to_srt, to_txt
from sokhan.core.quota import QuotaExceededError, ensure_quota
from sokhan.db import get_db
from sokhan.models import Job, JobStatus, Segment, User, utcnow
from sokhan.schemas import JobCreated, JobDetailOut, JobListResponse
from sokhan.worker.tasks import enqueue_job

router = APIRouter(prefix="/jobs", tags=["jobs"])

_ALLOWED_LANGUAGES = ("fa", "en", "auto")


def _get_owned_job(session: Session, job_id: str, user: User) -> Job:
    job = session.get(Job, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    return job


def _content_disposition(filename_base: str, extension: str) -> str:
    ascii_name = filename_base.encode("ascii", "ignore").decode() or "transcript"
    return (
        f'attachment; filename="{ascii_name}.{extension}"; '
        f"filename*=UTF-8''{quote(filename_base)}.{extension}"
    )


@router.post("", response_model=JobCreated, status_code=status.HTTP_201_CREATED)
def create_job(
    file: UploadFile = File(...),
    language: str = Form("fa"),
    want_summary: bool = Form(False),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> JobCreated:
    if language not in _ALLOWED_LANGUAGES:
        language = "fa"

    settings = get_settings()
    data = file.file.read()
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "empty file")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file too large")

    try:
        ensure_quota(
            session, user.id, utcnow(), settings.free_minutes_per_user_per_month
        )
    except QuotaExceededError as exc:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code": "quota_exceeded",
                "used_minutes": exc.used_minutes,
                "limit_minutes": exc.limit_minutes,
            },
        ) from exc

    job_id = str(uuid.uuid4())
    path = save_upload(data, job_id, file.filename or "upload")
    try:
        duration = probe_duration_seconds(path)
    except Exception as exc:
        delete_audio(path)
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "unsupported or corrupted audio file",
        ) from exc

    job = Job(
        id=job_id,
        user_id=user.id,
        filename=file.filename or "upload",
        stored_path=str(path),
        language=language,
        want_summary=want_summary,
        duration_seconds=duration,
        status=JobStatus.queued.value,
    )
    session.add(job)
    session.commit()
    enqueue_job(job_id)
    return JobCreated(id=job_id, status=job.status)


@router.get("", response_model=JobListResponse)
def list_jobs(
    limit: int = 100,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> JobListResponse:
    jobs = session.scalars(
        select(Job)
        .where(Job.user_id == user.id)
        .order_by(Job.created_at.desc())
        .limit(min(limit, 200))
    ).all()
    total = session.scalar(
        select(func.count()).select_from(Job).where(Job.user_id == user.id)
    )
    return JobListResponse(items=[job_to_out(job) for job in jobs], total=int(total or 0))


@router.get("/{job_id}", response_model=JobDetailOut)
def get_job(
    job_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> JobDetailOut:
    return job_to_detail(_get_owned_job(session, job_id, user))


@router.get("/{job_id}/summary")
def get_job_summary(
    job_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict:
    job = _get_owned_job(session, job_id, user)
    if job.summary is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no summary available")
    return {"summary": job.summary}


@router.get("/{job_id}/transcript")
def get_job_transcript(
    job_id: str,
    format: str = "txt",
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    job = _get_owned_job(session, job_id, user)
    if job.status != JobStatus.completed.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "job is not completed yet")

    segments = session.scalars(
        select(Segment).where(Segment.job_id == job_id).order_by(Segment.position)
    ).all()
    filename_base = job.filename.rsplit(".", 1)[0] or job.id

    if format == "txt":
        return Response(
            to_txt(list(segments)),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": _content_disposition(filename_base, "txt")},
        )
    if format == "srt":
        return Response(
            to_srt(list(segments)),
            media_type="application/x-subrip; charset=utf-8",
            headers={"Content-Disposition": _content_disposition(filename_base, "srt")},
        )
    if format == "docx":
        document = to_docx(list(segments), title=job.filename.rsplit(".", 1)[0] or "Transcript")
        return Response(
            document,
            media_type=(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
            headers={"Content-Disposition": _content_disposition(filename_base, "docx")},
        )
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "format must be txt, srt or docx")


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
    job_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> None:
    job = _get_owned_job(session, job_id, user)
    delete_audio(job.stored_path)
    session.delete(job)
    session.commit()
