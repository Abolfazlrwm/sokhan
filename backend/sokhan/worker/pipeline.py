"""Transcription pipeline executed by the worker (or inline when Celery is off).

decode -> chunk -> transcribe per chunk -> merge -> punctuation post-pass
-> persist segments and text -> optional summary -> usage record. Any error
flips the job to `failed` with the message stored on the row; a job never
dies silently.

Two decode modes: with `STREAMING_DECODE=true` (default) the audio is
decoded block-by-block while transcription runs, so peak RAM tracks the
30-second window instead of the file length — multi-hour recordings no
longer need RAM proportional to file size. The diarizers need the whole
signal at once, so any engine other than the stub (or an explicitly passed
diarizer) switches to the legacy full decode. Both paths produce the same
chunks (`test_streaming.py` proves it) and the same transcript.

Signed webhooks: when a job carries a callback_url, a completion/failure
event is POSTed after the database session closes, so a slow endpoint can
never hold a transaction open.
"""

import logging
import time
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import numpy as np
from sqlalchemy import delete

from sokhan.config import get_settings
from sokhan.core import formats
from sokhan.core.audio import (
    SAMPLE_RATE,
    decode_to_mono_16k,
    iter_mono_16k_blocks,
    probe_duration_seconds,
)
from sokhan.core.chunking import DEFAULT_OVERLAP_SECONDS, Chunk, chunk_samples, iter_chunks
from sokhan.core.fa_polish import polish_transcript
from sokhan.core.merge import merge_chunks
from sokhan.core.persian import normalize_for_search
from sokhan.core.punctuation import restore_punctuation
from sokhan.core.quota import record_usage
from sokhan.core.summary import Summarizer, get_summarizer
from sokhan.core.transcribe import Transcriber, get_transcriber, reports_progress
from sokhan.core.webhooks import build_payload, fire_job_callback
from sokhan.db import session_scope
from sokhan.diarization import Diarizer, SpeakerTurn, get_diarizer, label_segments
from sokhan.models import Job, JobStatus, Segment, utcnow

logger = logging.getLogger(__name__)


# Clock for throttling progress writes; a module attribute so tests can
# swap it without patching the process-wide `time.monotonic`.
_progress_clock = time.monotonic


def process_job(
    job_id: str,
    transcriber: Transcriber | None = None,
    summarizer: Summarizer | None = None,
    diarizer: Diarizer | None = None,
) -> str:
    """Run the full pipeline for one job; returns the final status string."""
    callback: dict[str, Any] | None = None
    final_status = JobStatus.failed.value
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
        speaker_engine = diarizer or get_diarizer()
        settings = get_settings()
        # Streaming decode keeps RAM proportional to the window instead of
        # the file. Whether it is allowed depends on the engine actually
        # built, not just the config: diarizers that need the whole signal
        # (energy, pyannote, test doubles) force the legacy full decode.
        streaming = settings.streaming_decode and not getattr(
            speaker_engine, "requires_full_audio", True
        )

        try:
            turns: list[SpeakerTurn] = []
            decoded_samples = 0
            estimated_duration: float | None = None
            stored_path = job.stored_path  # narrowed once: closures lose mypy narrowing

            if streaming:
                estimated_duration = probe_duration_seconds(
                    stored_path, allow_full_decode=False
                )

                def counted_blocks() -> Iterator[np.ndarray]:
                    nonlocal decoded_samples
                    for block in iter_mono_16k_blocks(stored_path):
                        decoded_samples += int(block.size)
                        yield block

                chunk_source: Iterator[Chunk] | list[Chunk] = iter_chunks(
                    counted_blocks(), SAMPLE_RATE, overlap_seconds=DEFAULT_OVERLAP_SECONDS
                )
                chunk_total: int | None = None
            else:
                samples = decode_to_mono_16k(job.stored_path)
                job.duration_seconds = len(samples) / SAMPLE_RATE
                try:
                    turns = speaker_engine.diarize(samples, SAMPLE_RATE)
                except Exception:
                    # Diarization is an enhancement, never a failure reason.
                    logger.warning(
                        "diarization failed for job %s; continuing without speaker labels",
                        job_id,
                        exc_info=True,
                    )
                chunk_source = chunk_samples(
                    samples, SAMPLE_RATE, overlap_seconds=DEFAULT_OVERLAP_SECONDS
                )
                chunk_total = len(chunk_source)

            chunk_segments = []
            chunk_starts = []
            last_saved_at = float("-inf")

            def save_progress(value: float) -> None:
                """Persist mid-chunk progress: monotonic, below 100, ~1/s."""
                nonlocal last_saved_at
                value = min(99.0, round(value, 1))
                now = _progress_clock()
                if value <= (job.progress or 0.0) or now - last_saved_at < 1.0:
                    return
                job.progress = value
                session.commit()
                last_saved_at = now

            for position, chunk in enumerate(chunk_source, start=1):
                chunk_starts.append(chunk.start)

                def chunk_progress(
                    fraction: float, position: int = position, chunk: Chunk = chunk
                ) -> None:
                    if chunk_total is not None:
                        save_progress((position - 1 + fraction) / chunk_total * 100.0)
                    elif estimated_duration:
                        done = chunk.start + fraction * (chunk.end - chunk.start)
                        save_progress(done / estimated_duration * 99.0)

                if reports_progress(engine):
                    segments = engine.transcribe(  # type: ignore[call-arg]
                        chunk.samples, SAMPLE_RATE, job.language, on_progress=chunk_progress
                    )
                else:
                    segments = engine.transcribe(chunk.samples, SAMPLE_RATE, job.language)
                chunk_segments.append(segments)
                if chunk_total is not None:
                    job.progress = round(position / chunk_total * 100.0, 1)
                elif estimated_duration:
                    job.progress = min(
                        99.0, round(chunk.end / estimated_duration * 99.0, 1)
                    )
                else:
                    # No length estimate available (headerless stream): still
                    # monotonic, converging towards 99 until the job ends.
                    job.progress = min(
                        99.0, round(position / (position + 1) * 99.0, 1)
                    )
                session.commit()

            total_duration = (
                decoded_samples / SAMPLE_RATE if streaming else len(samples) / SAMPLE_RATE
            )
            job.duration_seconds = total_duration

            merged = merge_chunks(
                chunk_segments,
                chunk_starts,
                DEFAULT_OVERLAP_SECONDS,
                total_duration,
            )
            if turns:
                label_segments(merged, turns)
            if settings.punctuation_enabled:
                merged = [
                    replace(segment, text=restore_punctuation(segment.text))
                    for segment in merged
                ]
            if settings.fa_polish:
                merged = [
                    replace(segment, text=polish_transcript(segment.text))
                    for segment in merged
                ]
            job.text = formats.to_txt(merged)
            job.text_normalized = normalize_for_search(job.text)
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
                        confidence=segment.confidence,
                    )
                )

            if job.want_summary:
                job.summary = summarizer.summarize(job.text)

            job.status = JobStatus.completed.value
            job.completed_at = utcnow()
            job.progress = 100.0
            record_usage(session, job.user_id, job_id, total_duration)
            if job.callback_url:
                # Built before commit on purpose: attributes are still live,
                # and payload construction can never flip the final status.
                callback = build_payload(job, "job.completed")
            session.commit()
            final_status = JobStatus.completed.value
        except Exception as exc:
            session.rollback()
            job = session.get(Job, job_id)
            if job is not None:
                job.status = JobStatus.failed.value
                job.error = str(exc)[:1000]
                if job.callback_url:
                    callback = build_payload(job, "job.failed", error=str(exc)[:1000])
                session.commit()
            logger.exception("job %s failed", job_id)
            final_status = JobStatus.failed.value

    # Outside the DB session on purpose: network I/O must never hold a
    # transaction open, and a dead endpoint must not fail the job.
    if callback is not None:
        fire_job_callback(callback)
    return final_status
