"""Runtime-editable config for the Settings page. Persists to a single-row DB table and
mutates the live `settings` singleton in place, so a change takes effect on the very next
request — no restart needed. (Every service reads `settings.X` fresh at call time, not a
cached copy, so this works without touching llm_research.py/news_sentiment.py etc.)
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import AppSettings

ROW_ID = 1


def _mask(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 4:
        return "*" * len(key)
    return f"{'*' * (len(key) - 4)}{key[-4:]}"


async def _get_row(session: AsyncSession) -> AppSettings | None:
    return (await session.execute(select(AppSettings).where(AppSettings.id == ROW_ID))).scalar_one_or_none()


async def load_settings_from_db(session: AsyncSession) -> None:
    """Called once at app startup: if a saved row exists, override the env defaults."""
    row = await _get_row(session)
    if row is None:
        return
    if row.deepseek_api_key:
        settings.DEEPSEEK_API_KEY = row.deepseek_api_key
    if row.news_cache_ttl_hours is not None:
        settings.NEWS_CACHE_TTL_HOURS = row.news_cache_ttl_hours
    if row.llm_cache_ttl_hours is not None:
        settings.LLM_CACHE_TTL_HOURS = row.llm_cache_ttl_hours


def get_settings_view() -> dict:
    """Current EFFECTIVE settings (the live singleton, post any override) — never the raw key."""
    return {
        "deepseek_api_key_set": bool(settings.DEEPSEEK_API_KEY),
        "deepseek_api_key_masked": _mask(settings.DEEPSEEK_API_KEY),
        "news_cache_ttl_hours": settings.NEWS_CACHE_TTL_HOURS,
        "llm_cache_ttl_hours": settings.LLM_CACHE_TTL_HOURS,
    }


async def update_settings(
    session: AsyncSession,
    deepseek_api_key: str | None = None,
    news_cache_ttl_hours: int | None = None,
    llm_cache_ttl_hours: int | None = None,
) -> dict:
    """Partial update: only fields actually passed (non-None) change. Persists + mutates
    the live singleton immediately."""
    row = await _get_row(session)
    if row is None:
        row = AppSettings(id=ROW_ID)
        session.add(row)

    if deepseek_api_key:
        row.deepseek_api_key = deepseek_api_key
        settings.DEEPSEEK_API_KEY = deepseek_api_key
    if news_cache_ttl_hours is not None:
        row.news_cache_ttl_hours = news_cache_ttl_hours
        settings.NEWS_CACHE_TTL_HOURS = news_cache_ttl_hours
    if llm_cache_ttl_hours is not None:
        row.llm_cache_ttl_hours = llm_cache_ttl_hours
        settings.LLM_CACHE_TTL_HOURS = llm_cache_ttl_hours

    await session.commit()
    return get_settings_view()
