"""Celery app instance."""
from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "quant_copilot",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]
# Asia/Shanghai (not UTC) because the earnings pipeline's beat schedule below is specified
# in China local time, matching the US pre/after-market earnings release peaks (8:00am ET /
# 4:30pm ET) it was originally tuned for. Nothing else in this app is timezone-sensitive yet.
celery_app.conf.timezone = "Asia/Shanghai"

# Ported from earnings-bot's crontab (0 20 * * * / 30 4 * * *) — CST 20:00 and 04:30.
celery_app.conf.beat_schedule = {
    "earnings-pipeline-evening": {
        "task": "run_earnings_pipeline",
        "schedule": crontab(hour=20, minute=0),
    },
    "earnings-pipeline-early": {
        "task": "run_earnings_pipeline",
        "schedule": crontab(hour=4, minute=30),
    },
}


@celery_app.task(name="ping")
def ping():
    """Smoke test task."""
    return "pong"


# Registers run_backtest_comparison / run_research_note with this app. Imported at the
# bottom (after `celery_app` exists) since backtest_tasks imports it back.
from app.tasks import backtest_tasks  # noqa: E402,F401

# Registers run_earnings_pipeline with this app, same reason.
from app.tasks import earnings_tasks  # noqa: E402,F401
