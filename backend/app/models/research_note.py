"""LLM-generated structured research notes per ticker."""
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ResearchNote(Base):
    __tablename__ = "research_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker_symbol: Mapped[str] = mapped_column(String(16), ForeignKey("tickers.symbol"), index=True)
    thesis: Mapped[str] = mapped_column(String)
    catalysts: Mapped[list] = mapped_column(JSON)
    risks: Mapped[list] = mapped_column(JSON)
    fair_value_low: Mapped[float] = mapped_column()
    fair_value_high: Mapped[float] = mapped_column()
    model: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
