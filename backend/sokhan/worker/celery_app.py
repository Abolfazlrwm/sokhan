"""Celery application wired to Redis.

See docs/adr/0002-queue-choice.md for why Celery (and when the inline
fallback is used instead).
"""

from celery import Celery

from sokhan.config import get_settings

settings = get_settings()

celery_app = Celery(
    "sokhan",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["sokhan.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    worker_hijack_root_logger=False,
)
