"""Single-row table persisting user-editable runtime config (Settings page, 连接与缓存 tab),
overriding the env-loaded defaults in app.config.settings without needing a restart.

Model provider/API-key/LLM-cache settings intentionally live in the research-lab config,
not here."""
from datetime import datetime

from sqlalchemy import DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AppSettings(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(primary_key=True)  # always row id=1
    news_cache_ttl_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
