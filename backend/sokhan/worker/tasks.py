"""Celery task wrapper plus the enqueue helper used by the API.

When CELERY_ENABLED=false the API runs the pipeline in a daemon thread so a
single `uvicorn` process can serve the full product without Redis. That mode
is meant for development and tiny self-hosted setups; production should run
the Celery worker.
"""

import threading

from sokhan.config import get_settings
from sokhan.worker.celery_app import celery_app
from sokhan.worker.pipeline import process_job


@celery_app.task(name="sokhan.process_job", max_retries=1)
def process_job_task(job_id: str) -> str:
    return process_job(job_id)


def enqueue_job(job_id: str) -> None:
    """Hand a job to Celery, or run it inline when Celery is disabled."""
    if get_settings().celery_enabled:
        process_job_task.delay(job_id)
    else:
        thread = threading.Thread(
            target=process_job, args=(job_id,), name=f"sokhan-job-{job_id}", daemon=True
        )
        thread.start()
