"""Daily equity log for the month-long systematic paper-trading simulation.

One row per (account, trading day). Lets us reconstruct each strategy's net-value curve
over the sim and compare it against the SPY buy-and-hold benchmark account.
"""
from datetime import date

from sqlalchemy import Date, Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SimEquity(Base):
    __tablename__ = "sim_equity"
    __table_args__ = (UniqueConstraint("account_id", "trade_date", name="uq_sim_equity_account_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_accounts.id"), index=True)
    trade_date: Mapped[date] = mapped_column(Date)
    equity: Mapped[float] = mapped_column(Float)
    cash: Mapped[float] = mapped_column(Float)
    positions_value: Mapped[float] = mapped_column(Float)
    num_positions: Mapped[int] = mapped_column(Integer)
