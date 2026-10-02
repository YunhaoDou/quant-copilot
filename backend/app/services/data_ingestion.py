"""Pulls adjusted OHLCV history via yfinance and upserts it into Postgres.

Mainland symbols use Yahoo Finance suffixes such as ``600519.SS`` and ``000858.SZ``.
"""
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Price, Ticker

COLUMNS = ["trade_date", "open", "high", "low", "close", "volume"]


def _normalize_date(value: str) -> str:
    """Accept both '20140101' and '2014-01-01'; return ISO 'YYYY-MM-DD' for yfinance."""
    value = value.strip()
    if "-" in value:
        return value
    return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"


def fetch_history(symbol: str, start: str = "20140101", end: str | None = None) -> pd.DataFrame:
    """Fetch adjusted daily bars for a ticker as a normalized DataFrame."""
    raw = yf.Ticker(symbol.upper()).history(
        start=_normalize_date(start),
        end=_normalize_date(end) if end else None,
        auto_adjust=True,
    )
    if raw.empty:
        return pd.DataFrame(columns=COLUMNS)

    raw = raw.reset_index().rename(
        columns={
            "Date": "trade_date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )
    df = raw[COLUMNS].copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    return df


async def ingest_ticker(
    session: AsyncSession, symbol: str, name: str, market: str = "US", start: str = "20140101"
) -> int:
    """Fetch full history for ``symbol`` and upsert rows. Returns row count upserted."""
    symbol = symbol.upper()
    df = fetch_history(symbol, start=start)
    if df.empty:
        return 0

    result = await session.execute(select(Ticker).where(Ticker.symbol == symbol))
    ticker = result.scalar_one_or_none()
    if ticker is None:
        ticker = Ticker(symbol=symbol, name=name, market=market)
        session.add(ticker)
        await session.flush()

    rows = df.to_dict("records")
    for row in rows:
        row["ticker_symbol"] = symbol
        # Coerce numpy scalars to native python types for asyncpg.
        row["open"] = float(row["open"])
        row["high"] = float(row["high"])
        row["low"] = float(row["low"])
        row["close"] = float(row["close"])
        row["volume"] = float(row["volume"])

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
    symbol = symbol.upper()
    result = await session.execute(
        select(Price.trade_date, Price.close).where(Price.ticker_symbol == symbol).order_by(Price.trade_date)
    )
    rows = result.all()
    if not rows:
        return pd.Series(dtype=float)
    idx = pd.DatetimeIndex([r.trade_date for r in rows])
    return pd.Series([r.close for r in rows], index=idx, name=symbol)


async def load_ohlcv(session: AsyncSession, symbol: str) -> pd.DataFrame:
    """Load a ticker's full stored OHLCV history, indexed by date — shared by any service
    that needs more than just closes (fund-flow, screening factors, etc.)."""
    symbol = symbol.upper()
    rows = (
        await session.execute(
            select(Price.trade_date, Price.open, Price.high, Price.low, Price.close, Price.volume)
            .where(Price.ticker_symbol == symbol)
            .order_by(Price.trade_date)
        )
    ).all()
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    idx = pd.DatetimeIndex([r.trade_date for r in rows])
    return pd.DataFrame(
        {
            "open": [r.open for r in rows],
            "high": [r.high for r in rows],
            "low": [r.low for r in rows],
            "close": [r.close for r in rows],
            "volume": [r.volume for r in rows],
        },
        index=idx,
    )
