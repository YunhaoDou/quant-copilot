"""Pulls real A-share OHLCV history via akshare (Sina-backed, `stock_zh_a_daily`) and
upserts it into Postgres. The Eastmoney-backed `stock_zh_a_hist` endpoint was tested and
found unreliable from this network (connection resets); Sina's endpoint is stable.
"""
from datetime import date, datetime, timezone

import akshare as ak
import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Price, Ticker


def _prefixed_symbol(symbol: str) -> str:
    """akshare's Sina-backed API wants an exchange prefix: 6xxxxx -> sh, 0/3xxxxx -> sz."""
    if symbol.startswith(("sh", "sz")):
        return symbol
    return f"sh{symbol}" if symbol.startswith("6") else f"sz{symbol}"


def fetch_history(symbol: str, start: str = "20140101", end: str | None = None) -> pd.DataFrame:
    end = end or date.today().strftime("%Y%m%d")
    df = ak.stock_zh_a_daily(symbol=_prefixed_symbol(symbol), start_date=start, end_date=end, adjust="qfq")
    df = df.rename(columns={"date": "trade_date"})[["trade_date", "open", "high", "low", "close", "volume"]]
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    return df


async def ingest_ticker(session: AsyncSession, symbol: str, name: str, start: str = "20140101") -> int:
    """Fetch full history for a bare 6-digit `symbol` and upsert rows. Returns row count upserted."""
    df = fetch_history(symbol, start=start)
    if df.empty:
        return 0

    result = await session.execute(select(Ticker).where(Ticker.symbol == symbol))
    ticker = result.scalar_one_or_none()
    if ticker is None:
        ticker = Ticker(symbol=symbol, name=name, market="A")
        session.add(ticker)
        await session.flush()

    rows = df.to_dict("records")
    for row in rows:
        row["ticker_symbol"] = symbol

    stmt = insert(Price).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ticker_symbol", "trade_date"],
        set_={
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "volume": stmt.excluded.volume,
        },
    )
    await session.execute(stmt)

    ticker.last_synced_at = datetime.now(timezone.utc)
    await session.commit()
    return len(rows)


async def load_price_series(session: AsyncSession, symbol: str) -> pd.Series:
    """Load a ticker's stored close-price series, indexed by date, for backtesting."""
    result = await session.execute(
        select(Price.trade_date, Price.close).where(Price.ticker_symbol == symbol).order_by(Price.trade_date)
    )
    rows = result.all()
    if not rows:
        return pd.Series(dtype=float)
    idx = pd.DatetimeIndex([r.trade_date for r in rows])
    return pd.Series([r.close for r in rows], index=idx, name=symbol)
