"""Persisted multi-factor screening score per ticker per day."""
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StockScore(Base):
    __tablename__ = "stock_scores"
    __table_args__ = (
        Index("ix_stock_scores_ticker_date", "ticker_symbol", "as_of_date", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker_symbol: Mapped[str] = mapped_column(String(16), ForeignKey("tickers.symbol"), index=True)
    as_of_date: Mapped[date] = mapped_column(Date)
    composite_score: Mapped[float] = mapped_column(Float)
    rank: Mapped[int] = mapped_column(Integer)
    factors: Mapped[dict] = mapped_column(JSON)
    reasons: Mapped[list] = mapped_column(JSON)
    method: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
