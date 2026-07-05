"""Ticker universe and price-history endpoints (M1 data foundation)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Price, Ticker
from app.services import data_ingestion

router = APIRouter(prefix="/tickers", tags=["tickers"])


@router.post("/{symbol}/ingest")
async def ingest(
    symbol: str, name: str, start: str = "20140101", session: AsyncSession = Depends(get_session)
):
    try:
        count = await data_ingestion.ingest_ticker(session, symbol, name, start=start)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ingestion failed: {exc}") from exc
    if count == 0:
        raise HTTPException(status_code=404, detail="no data returned for this symbol")
    return {"symbol": symbol, "rows_upserted": count}


@router.get("")
async def list_tickers(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Ticker))
    return [
        {"symbol": t.symbol, "name": t.name, "market": t.market, "last_synced_at": t.last_synced_at}
        for t in result.scalars()
    ]


@router.get("/{symbol}/prices")
async def get_prices(symbol: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Price.trade_date, Price.open, Price.high, Price.low, Price.close, Price.volume)
        .where(Price.ticker_symbol == symbol)
        .order_by(Price.trade_date)
    )
    rows = result.all()
    if not rows:
        raise HTTPException(status_code=404, detail="no price data ingested for this symbol yet")
    return [
        {
            "date": r.trade_date.isoformat(),
            "open": r.open,
            "high": r.high,
            "low": r.low,
            "close": r.close,
            "volume": r.volume,
        }
        for r in rows
    ]
