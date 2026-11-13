"""OpenAI-compatible transcription endpoint.

Drop-in replacement for POST /v1/audio/transcriptions: accepts multipart
`file` with optional `language` and `response_format` (json | text | srt |
verbose_json), authenticates with the same bearer token, runs inline in the
request threadpool and records usage against the monthly quota. For long
recordings prefer POST /jobs, which queues the work instead of blocking.
"""

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from sokhan.api.deps import get_current_user
from sokhan.config import get_settings
from sokhan.core.audio import SAMPLE_RATE, decode_to_mono_16k, delete_audio, save_upload
from sokhan.core.chunking import DEFAULT_OVERLAP_SECONDS, chunk_samples
from sokhan.core.formats import to_srt, to_txt
from sokhan.core.merge import merge_chunks
from sokhan.core.quota import QuotaExceededError, ensure_quota, record_usage
from sokhan.core.transcribe import get_transcriber
from sokhan.db import get_db
from sokhan.models import User, utcnow

router = APIRouter(prefix="/v1", tags=["openai-compatible"])

_FORMATS = ("json", "text", "srt", "verbose_json")


@router.post("/audio/transcriptions")
def transcribe_audio(
    file: UploadFile = File(...),
    model: str = Form("sokhan"),
    language: str = Form("fa"),
    response_format: str = Form("json"),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    if response_format not in _FORMATS:
        raise HTTPException(422, f"response_format must be one of: {', '.join(_FORMATS)}")

    settings = get_settings()
    data = file.file.read()
    if not data:
        raise HTTPException(422, "empty file")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, "file too large")

    try:
        ensure_quota(session, user.id, utcnow(), settings.free_minutes_per_user_per_month)
    except QuotaExceededError as exc:
        raise HTTPException(
            402,
            detail={
                "code": "quota_exceeded",
                "used_minutes": exc.used_minutes,
                "limit_minutes": exc.limit_minutes,
            },
        ) from exc

    temp_id = f"inline-{uuid.uuid4()}"
    path = save_upload(data, temp_id, file.filename or "audio")
    try:
        samples = decode_to_mono_16k(path)
    except Exception as exc:
        delete_audio(path)
        raise HTTPException(422, "unsupported or corrupted audio file") from exc

    duration = len(samples) / SAMPLE_RATE
    chunks = chunk_samples(samples, SAMPLE_RATE, overlap_seconds=DEFAULT_OVERLAP_SECONDS)
    transcriber = get_transcriber()
    chunk_segments = [
        transcriber.transcribe(chunk.samples, SAMPLE_RATE, language) for chunk in chunks
    ]
    merged = merge_chunks(
        chunk_segments,
        [chunk.start for chunk in chunks],
        DEFAULT_OVERLAP_SECONDS,
        duration,
    )
    record_usage(session, user.id, None, duration)
    session.commit()
    delete_audio(path)

    used_model = f"whisper-{settings.whisper_model_size}"
    text = to_txt(merged)

    if response_format == "text":
        return Response(text, media_type="text/plain; charset=utf-8")
    if response_format == "srt":
        return Response(to_srt(merged), media_type="application/x-subrip; charset=utf-8")

    segments_payload = [
        {"id": index, "start": segment.start, "end": segment.end, "text": segment.text}
        for index, segment in enumerate(merged)
    ]
    if response_format == "verbose_json":
        return {
            "text": text,
            "model": used_model,
            "language": language,
            "duration": round(duration, 3),
            "segments": segments_payload,
        }
    return {"text": text, "model": used_model}
