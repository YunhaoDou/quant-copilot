"""A-share fund universe and NAV history (AKShare-backed) — a separate asset class from
the US-equity Ticker/Price pipeline (see data_ingestion.py's note on why that one is
yfinance-only). OTC funds carry nav/acc_nav; on-exchange ETF/LOF funds also carry a
traded close price. Premium/discount vs IOPV is computed live (see services/fund_analysis.py)
rather than stored per-day, since it needs a same-moment price+IOPV pair, not history.
"""
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Fund(Base):
    __tablename__ = "funds"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    fund_type: Mapped[str] = mapped_column(String(16))  # ETF / LOF / OTC
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FundNav(Base):
    """Daily NAV/price bar. ETF/LOF rows carry `close`; OTC rows carry `nav`/`acc_nav`."""

    __tablename__ = "fund_navs"
    __table_args__ = (Index("ix_fund_navs_code_date", "fund_code", "nav_date", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    fund_code: Mapped[str] = mapped_column(String(16), ForeignKey("funds.code"), index=True)
    nav_date: Mapped[date] = mapped_column(Date)
    nav: Mapped[float | None] = mapped_column(Float, nullable=True)
    acc_nav: Mapped[float | None] = mapped_column(Float, nullable=True)
    close: Mapped[float | None] = mapped_column(Float, nullable=True)
