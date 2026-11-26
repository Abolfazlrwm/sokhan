"""Job lifecycle: upload, status, transcripts, summary and delete."""

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sokhan.api.deps import get_current_user
from sokhan.api.limits import ensure_file_cap, ensure_monthly_quota, resolve_plan
from sokhan.api.serializers import job_to_detail, job_to_out
from sokhan.config import get_settings
from sokhan.core.audio import delete_audio, probe_duration_seconds, save_upload
from sokhan.core.formats import to_docx, to_json_transcript, to_srt, to_txt, to_vtt
from sokhan.core.webhooks import callback_url_problem
from sokhan.db import get_db
from sokhan.models import Job, JobStatus, Segment, User
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
    callback_url: str | None = Form(None),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> JobCreated:
    if language not in _ALLOWED_LANGUAGES:
        language = "fa"

    if callback_url is not None:
        callback_url = callback_url.strip() or None
    settings = get_settings()
    if callback_url:
        if len(callback_url) > 2048:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "callback_url must be an http(s) URL of at most 2048 characters",
            )
        problem = callback_url_problem(callback_url, settings.webhook_allow_private_targets)
        if problem:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, problem)
    data = file.file.read()
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "empty file")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file too large")

    plan = resolve_plan(user)
    # Cheap monthly gate first, before the audio touches the disk.
    ensure_monthly_quota(session, user, plan)

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

    # Per-file duration cap of the plan; the stored file must not leak on
    # rejection, so it is deleted before the 402 goes out.
    try:
        ensure_file_cap(plan, duration)
    except HTTPException:
        delete_audio(path)
        raise

    job = Job(
        id=job_id,
        user_id=user.id,
        filename=file.filename or "upload",
        stored_path=str(path),
        language=language,
        want_summary=want_summary,
        callback_url=callback_url,
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
    review_threshold: float | None = get_settings().low_confidence_threshold

    if format == "txt":
        return Response(
            to_txt(list(segments)),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": _content_disposition(filename_base, "txt")},
        )
    if format == "srt":
        return Response(
            to_srt(list(segments), low_confidence_below=review_threshold),
            media_type="application/x-subrip; charset=utf-8",
            headers={"Content-Disposition": _content_disposition(filename_base, "srt")},
        )
    if format == "vtt":
        return Response(
            to_vtt(list(segments), low_confidence_below=review_threshold),
            media_type="text/vtt; charset=utf-8",
            headers={"Content-Disposition": _content_disposition(filename_base, "vtt")},
        )
    if format == "json":
        return Response(
            to_json_transcript(
                list(segments),
                filename=job.filename,
                language=job.language,
                duration_seconds=job.duration_seconds,
            ),
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": _content_disposition(filename_base, "json")},
        )
    if format == "docx":
        document = to_docx(
            list(segments),
            title=job.filename.rsplit(".", 1)[0] or "Transcript",
            low_confidence_below=review_threshold,
        )
        return Response(
            document,
            media_type=(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
            headers={"Content-Disposition": _content_disposition(filename_base, "docx")},
        )
    raise HTTPException(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "format must be txt, srt, vtt, json or docx",
    )


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
