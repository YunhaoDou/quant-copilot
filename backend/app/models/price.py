"""Daily OHLCV price bars. BRIN-indexed on date for time-series scan efficiency."""
from datetime import date

from sqlalchemy import Date, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Price(Base):
    __tablename__ = "prices"
    __table_args__ = (
        Index("ix_prices_ticker_date", "ticker_symbol", "trade_date", unique=True),
        Index("ix_prices_date_brin", "trade_date", postgresql_using="brin"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker_symbol: Mapped[str] = mapped_column(String(16), ForeignKey("tickers.symbol"), index=True)
    trade_date: Mapped[date] = mapped_column(Date)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
