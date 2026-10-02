"""Single-row table persisting user-editable runtime config (Settings page), overriding
the env-loaded defaults in app.config.settings without needing a restart."""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AppSettings(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(primary_key=True)  # always row id=1
    deepseek_api_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    news_cache_ttl_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_cache_ttl_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
