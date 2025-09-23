# backend/celery_app.py
from celery import Celery
import os

broker_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
backend_url = broker_url  # dùng Redis làm result backend tối thiểu

celery_app = Celery(
    "tts_vtn",
    broker=broker_url,
    backend=backend_url,
)

# (tùy chọn) cấu hình khi test để không cần Redis thực (sẽ monkeypatch trong test)
celery_app.conf.update(
    task_track_started=True,
    result_extended=True,
)
