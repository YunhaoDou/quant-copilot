"""Celery app instance. Phase 0 placeholder; tasks added in later phases."""
from celery import Celery

from app.config import settings

celery_app = Celery(
    "quant_copilot",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]
celery_app.conf.timezone = "UTC"


@celery_app.task(name="ping")
def ping():
    """Smoke test task."""
    return "pong"
