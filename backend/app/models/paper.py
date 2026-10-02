"""M4 paper trading: cash accounts, orders, and positions.

Orders execute synchronously against the latest ingested close price — this is a
research/paper-trading sandbox, not a live matching engine. Market orders always fill;
limit and stop orders fill only when they are marketable against the latest close,
otherwise they are rejected (no resting-order book at this milestone).
"""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PaperAccount(Base):
    __tablename__ = "paper_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    starting_cash: Mapped[float] = mapped_column(Float)
    cash_balance: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PaperOrder(Base):
    __tablename__ = "paper_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_accounts.id"), index=True)
    ticker_symbol: Mapped[str] = mapped_column(String(16), ForeignKey("tickers.symbol"))
    side: Mapped[str] = mapped_column(String(4))  # buy / sell
    order_type: Mapped[str] = mapped_column(String(8))  # market / limit / stop
    quantity: Mapped[int] = mapped_column(Integer)
    limit_price: Mapped[float | None] = mapped_column(Float, nullable=True)  # limit/stop trigger
    status: Mapped[str] = mapped_column(String(12))  # filled / rejected
    fill_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(128), nullable=True)  # why rejected
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PaperPosition(Base):
    __tablename__ = "paper_positions"
    __table_args__ = (UniqueConstraint("account_id", "ticker_symbol", name="uq_position_account_ticker"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_accounts.id"), index=True)
    ticker_symbol: Mapped[str] = mapped_column(String(16), ForeignKey("tickers.symbol"))
    quantity: Mapped[int] = mapped_column(Integer)
    avg_cost: Mapped[float] = mapped_column(Float)
