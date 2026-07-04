"""A single backtest run and its resulting equity curve."""
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker_symbol: Mapped[str] = mapped_column(String(16), ForeignKey("tickers.symbol"), index=True)
    strategy_key: Mapped[str] = mapped_column(String(32), ForeignKey("strategies.key"))
    params: Mapped[dict] = mapped_column(JSON)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    total_return: Mapped[float] = mapped_column(Float)
    sharpe_ratio: Mapped[float] = mapped_column(Float)
    max_drawdown: Mapped[float] = mapped_column(Float)
    win_rate: Mapped[float] = mapped_column(Float)
    num_trades: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BacktestCurve(Base):
    __tablename__ = "backtest_curves"

    id: Mapped[int] = mapped_column(primary_key=True)
    backtest_run_id: Mapped[int] = mapped_column(ForeignKey("backtest_runs.id"), index=True)
    trade_date: Mapped[date] = mapped_column(Date)
    equity: Mapped[float] = mapped_column(Float)
