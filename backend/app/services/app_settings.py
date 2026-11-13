"""Runtime-editable config for the Settings page (连接与缓存 tab). Persists to a single-row
DB table and mutates the live `settings` singleton in place, so a change takes effect on the
very next request — no restart needed.

Only the news cache TTL is stored here. Model provider/API-key/LLM-cache configuration is
owned by the research-lab config (`/research-lab/config`, 模型与通知 tab); this module must
not carry a second copy of it.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import AppSettings

ROW_ID = 1


async def _get_row(session: AsyncSession) -> AppSettings | None:
    return (await session.execute(select(AppSettings).where(AppSettings.id == ROW_ID))).scalar_one_or_none()


async def load_settings_from_db(session: AsyncSession) -> None:
    """Called once at app startup: if a saved row exists, override the env defaults."""
    row = await _get_row(session)
    if row is None:
        return
    if row.news_cache_ttl_hours is not None:
        settings.NEWS_CACHE_TTL_HOURS = row.news_cache_ttl_hours


def get_settings_view() -> dict:
    """Current EFFECTIVE settings (the live singleton, post any override)."""
    return {
        "news_cache_ttl_hours": settings.NEWS_CACHE_TTL_HOURS,
    }


async def update_settings(
    session: AsyncSession,
    news_cache_ttl_hours: int | None = None,
) -> dict:
    """Partial update: only fields actually passed (non-None) change. Persists + mutates
    the live singleton immediately."""
    row = await _get_row(session)
    if row is None:
        row = AppSettings(id=ROW_ID)
        session.add(row)

    if news_cache_ttl_hours is not None:
        row.news_cache_ttl_hours = news_cache_ttl_hours
        settings.NEWS_CACHE_TTL_HOURS = news_cache_ttl_hours

    await session.commit()
    return get_settings_view()
