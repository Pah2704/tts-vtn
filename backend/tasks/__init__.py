"""Task package exports for Celery autodiscovery."""

# Đảm bảo package được nhận diện và tasks được import khi autodiscover
from .tasks import generate_task  # noqa: F401
from .xtts_task import *  # noqa: F401,F403

__all__ = ["generate_task"]
