"""Celery application bootstrap for tts_vtn."""

from __future__ import annotations

import os

from celery import Celery


broker_url = (
    os.getenv("CELERY_BROKER_URL")
    or os.getenv("REDIS_URL")
    or "redis://redis:6379/0"
)
result_backend = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")

celery = Celery("tts_vtn", broker=broker_url, backend=result_backend)
celery.conf.update(
    broker_url=broker_url,
    result_backend=result_backend,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_time_limit=int(os.getenv("CELERY_TASK_TIME_LIMIT", "3600")),
    broker_connection_retry_on_startup=True,
    task_always_eager=os.getenv("CELERY_TASK_ALWAYS_EAGER") == "1",
)

# Autodiscover Celery tasks defined under backend.tasks.*
celery.autodiscover_tasks(["backend.tasks"])


__all__ = ["celery"]
