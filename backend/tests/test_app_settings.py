"""Settings-page tests: mutation takes effect on the live singleton immediately, persists
to DB, survives a simulated restart (reload from DB), and never round-trips the raw key."""
import pytest

from app.config import settings
from app.services import app_settings

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def restore_settings():
    """Snapshot/restore the process-wide settings singleton so tests don't leak into each other."""
    original = (settings.DEEPSEEK_API_KEY, settings.NEWS_CACHE_TTL_HOURS, settings.LLM_CACHE_TTL_HOURS)
    yield
    settings.DEEPSEEK_API_KEY, settings.NEWS_CACHE_TTL_HOURS, settings.LLM_CACHE_TTL_HOURS = original


async def test_update_mutates_live_singleton_immediately(db_session):
    await app_settings.update_settings(db_session, news_cache_ttl_hours=7)
    assert settings.NEWS_CACHE_TTL_HOURS == 7


async def test_update_is_partial_unspecified_fields_untouched(db_session):
    await app_settings.update_settings(db_session, news_cache_ttl_hours=7)
    await app_settings.update_settings(db_session, llm_cache_ttl_hours=48)
    assert settings.NEWS_CACHE_TTL_HOURS == 7  # untouched by the second call
    assert settings.LLM_CACHE_TTL_HOURS == 48


async def test_api_key_never_returned_in_full():
    settings.DEEPSEEK_API_KEY = "sk-abcdefghijklmnop"
    view = app_settings.get_settings_view()
    assert view["deepseek_api_key_set"] is True
    assert "sk-abcdefghijklmnop" not in view["deepseek_api_key_masked"]
    assert view["deepseek_api_key_masked"].endswith("mnop")


async def test_empty_key_update_leaves_existing_key_untouched(db_session):
    settings.DEEPSEEK_API_KEY = "sk-original"
    await app_settings.update_settings(db_session, deepseek_api_key=None)
    assert settings.DEEPSEEK_API_KEY == "sk-original"
    await app_settings.update_settings(db_session, deepseek_api_key="")
    assert settings.DEEPSEEK_API_KEY == "sk-original"  # blank string is a no-op, not a wipe


async def test_persisted_row_reloads_into_singleton_on_startup(db_session):
    settings.DEEPSEEK_API_KEY = "sk-should-be-overwritten"
    await app_settings.update_settings(db_session, deepseek_api_key="sk-persisted-value", news_cache_ttl_hours=9)

    # simulate a fresh process: reset the in-memory singleton, then reload from DB
    settings.DEEPSEEK_API_KEY = "sk-env-default"
    settings.NEWS_CACHE_TTL_HOURS = 2
    await app_settings.load_settings_from_db(db_session)

    assert settings.DEEPSEEK_API_KEY == "sk-persisted-value"
    assert settings.NEWS_CACHE_TTL_HOURS == 9


async def test_load_from_db_is_noop_when_no_row_saved_yet(db_session):
    settings.DEEPSEEK_API_KEY = "sk-env-default"
    await app_settings.load_settings_from_db(db_session)
    assert settings.DEEPSEEK_API_KEY == "sk-env-default"
