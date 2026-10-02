"""Persisted fund-flow (money-in/money-out) signal per ticker per day."""
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FundFlowSignal(Base):
    __tablename__ = "fund_flow_signals"
    __table_args__ = (
        Index("ix_fund_flow_ticker_date", "ticker_symbol", "as_of_date", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker_symbol: Mapped[str] = mapped_column(String(16), ForeignKey("tickers.symbol"), index=True)
    as_of_date: Mapped[date] = mapped_column(Date)
    signal: Mapped[str] = mapped_column(String(16))
    score: Mapped[float] = mapped_column(Float)
    cmf: Mapped[float] = mapped_column(Float)
    mfi: Mapped[float] = mapped_column(Float)
    obv_trend: Mapped[str] = mapped_column(String(8))
    large_volume_bias: Mapped[float] = mapped_column(Float)
    window_days: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
