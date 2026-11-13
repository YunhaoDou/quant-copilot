"""Settings-page endpoint: view/edit runtime config (连接与缓存 tab: news cache TTL).
Model provider/API-key/LLM-cache config is served by /research-lab/config (模型与通知 tab)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services import app_settings

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    news_cache_ttl_hours: int | None = None


@router.get("")
def get_settings():
    return app_settings.get_settings_view()


@router.put("")
async def update_settings(req: SettingsUpdate, session: AsyncSession = Depends(get_session)):
    return await app_settings.update_settings(
        session,
        news_cache_ttl_hours=req.news_cache_ttl_hours,
    )
