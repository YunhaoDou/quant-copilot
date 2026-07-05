"""Celery app instance."""
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


# Registers run_backtest_comparison / run_research_note with this app. Imported at the
# bottom (after `celery_app` exists) since backtest_tasks imports it back.
from app.tasks import backtest_tasks  # noqa: E402,F401
