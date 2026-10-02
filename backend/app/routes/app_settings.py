"""Settings-page endpoint: view/edit runtime config (DeepSeek key, cache TTLs). The API
key is never round-tripped in full — GET returns a masked view, and PUT only changes it
if the caller actually sends a new value."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services import app_settings

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    deepseek_api_key: str | None = None
    news_cache_ttl_hours: int | None = None
    llm_cache_ttl_hours: int | None = None


@router.get("")
def get_settings():
    return app_settings.get_settings_view()


@router.put("")
async def update_settings(req: SettingsUpdate, session: AsyncSession = Depends(get_session)):
    return await app_settings.update_settings(
        session,
        deepseek_api_key=req.deepseek_api_key,
        news_cache_ttl_hours=req.news_cache_ttl_hours,
        llm_cache_ttl_hours=req.llm_cache_ttl_hours,
    )
