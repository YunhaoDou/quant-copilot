"""Settings-page tests (连接与缓存 tab).

Only the news cache TTL is editable here; model provider/API-key/LLM-cache configuration
lives in the research-lab config (/research-lab/config) and must not be duplicated.
The TTL mutation takes effect on the live singleton immediately, persists to DB, and
survives a simulated restart (reload from DB).
"""
import pytest

from app.config import settings
from app.services import app_settings

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def restore_settings():
    """Snapshot/restore the process-wide settings singleton so tests don't leak into each other."""
    original = settings.NEWS_CACHE_TTL_HOURS
    yield
    settings.NEWS_CACHE_TTL_HOURS = original


async def test_update_mutates_live_singleton_immediately(db_session):
    await app_settings.update_settings(db_session, news_cache_ttl_hours=7)
    assert settings.NEWS_CACHE_TTL_HOURS == 7


async def test_update_with_no_fields_leaves_value_untouched(db_session):
    await app_settings.update_settings(db_session, news_cache_ttl_hours=7)
    await app_settings.update_settings(db_session)
    assert settings.NEWS_CACHE_TTL_HOURS == 7


async def test_settings_view_only_exposes_the_news_cache_ttl():
    view = app_settings.get_settings_view()
    assert set(view) == {"news_cache_ttl_hours"}
    assert view["news_cache_ttl_hours"] == settings.NEWS_CACHE_TTL_HOURS


async def test_persisted_row_reloads_into_singleton_on_startup(db_session):
    await app_settings.update_settings(db_session, news_cache_ttl_hours=9)

    # simulate a fresh process: reset the in-memory singleton, then reload from DB
    settings.NEWS_CACHE_TTL_HOURS = 2
    await app_settings.load_settings_from_db(db_session)

    assert settings.NEWS_CACHE_TTL_HOURS == 9


async def test_load_from_db_is_noop_when_no_row_saved_yet(db_session):
    settings.NEWS_CACHE_TTL_HOURS = 2
    await app_settings.load_settings_from_db(db_session)
    assert settings.NEWS_CACHE_TTL_HOURS == 2
