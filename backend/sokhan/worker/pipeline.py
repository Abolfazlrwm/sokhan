"""Transcription pipeline executed by the worker (or inline when Celery is off).

decode -> chunk -> transcribe per chunk -> merge -> persist segments and text
-> optional summary -> usage record. Any error flips the job to `failed` with
the message stored on the row; a job never dies silently.
"""

import logging

from sqlalchemy import delete

from sokhan.core import formats
from sokhan.core.audio import SAMPLE_RATE, decode_to_mono_16k
from sokhan.core.chunking import DEFAULT_OVERLAP_SECONDS, chunk_samples
from sokhan.core.merge import merge_chunks
from sokhan.core.persian import normalize_persian
from sokhan.core.quota import record_usage
from sokhan.core.summary import Summarizer, get_summarizer
from sokhan.core.transcribe import Transcriber, get_transcriber
from sokhan.db import session_scope
from sokhan.models import Job, JobStatus, Segment, utcnow

logger = logging.getLogger(__name__)


def process_job(
    job_id: str,
    transcriber: Transcriber | None = None,
    summarizer: Summarizer | None = None,
) -> str:
    """Run the full pipeline for one job; returns the final status string."""
    with session_scope() as session:
        job = session.get(Job, job_id)
        if job is None:
            logger.error("job %s not found", job_id)
            return JobStatus.failed.value
        if job.status in (JobStatus.completed.value, JobStatus.processing.value):
            # Already handled (or being handled by another worker).
            return job.status

        job.status = JobStatus.processing.value
        session.commit()

        engine = transcriber or get_transcriber()
        summarizer = summarizer or get_summarizer()

        try:
            samples = decode_to_mono_16k(job.stored_path)
            total_duration = len(samples) / SAMPLE_RATE
            job.duration_seconds = total_duration
            chunks = chunk_samples(
                samples, SAMPLE_RATE, overlap_seconds=DEFAULT_OVERLAP_SECONDS
            )

            chunk_segments = []
            for position, chunk in enumerate(chunks, start=1):
                chunk_segments.append(
                    engine.transcribe(chunk.samples, SAMPLE_RATE, job.language)
                )
                job.progress = round(position / len(chunks) * 100.0, 1)
                session.commit()

            merged = merge_chunks(
                chunk_segments,
                [chunk.start for chunk in chunks],
                DEFAULT_OVERLAP_SECONDS,
                total_duration,
            )
            job.text = formats.to_txt(merged)
            job.text_normalized = normalize_persian(job.text)
            session.execute(delete(Segment).where(Segment.job_id == job_id))
            for position, segment in enumerate(merged):
                session.add(
                    Segment(
                        job_id=job_id,
                        position=position,
                        start=segment.start,
                        end=segment.end,
                        text=segment.text,
                        speaker=segment.speaker,
                    )
                )

            if job.want_summary:
                job.summary = summarizer.summarize(job.text)

            job.status = JobStatus.completed.value
            job.completed_at = utcnow()
            job.progress = 100.0
            record_usage(session, job.user_id, job_id, total_duration)
            session.commit()
            return JobStatus.completed.value
        except Exception as exc:
            session.rollback()
            job = session.get(Job, job_id)
            if job is not None:
                job.status = JobStatus.failed.value
                job.error = str(exc)[:1000]
                session.commit()
            logger.exception("job %s failed", job_id)
            return JobStatus.failed.value
