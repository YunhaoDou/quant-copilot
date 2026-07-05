"""Strategy templates available to the backtest engine."""
from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(32), unique=True)  # e.g. "sma_crossover"
    name: Mapped[str] = mapped_column(String(128))
    default_params: Mapped[dict] = mapped_column(JSON)
