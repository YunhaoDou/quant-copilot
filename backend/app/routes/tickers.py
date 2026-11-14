"""Ticker universe and price-history endpoints (M1 data foundation)."""
from fastapi import APIRouter, Depends, HTTPException, Request
import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Price, Ticker
from app.services import data_ingestion

router = APIRouter(prefix="/tickers", tags=["tickers"])


@router.post("/{symbol}/ingest")
async def ingest(
    symbol: str,
    name: str,
    market: str = "CN",
    start: str = "20140101",
    session: AsyncSession = Depends(get_session),
):
    try:
        count = await data_ingestion.ingest_ticker(session, symbol, name, market=market, start=start)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ingestion failed: {exc}") from exc
    if count == 0:
        raise HTTPException(status_code=404, detail="no data returned for this symbol")
    return {"symbol": symbol, "rows_upserted": count}


@router.get("")
async def list_tickers(request: Request, session: AsyncSession = Depends(get_session)):
    from app.cycle.all_a import saved
    from app.cycle.etf_universe import saved as etf_saved
    from app.cycle import read_cache,events
    universe,universe_version=await asyncio.to_thread(read_cache.document,events.DB_PATH,"all_a_universe")
    if not universe:raise HTTPException(503,"官方全A股名单尚未就绪，请更新全市场数据")
    result=await session.execute(select(Ticker))
    stored={t.symbol.split('.')[0]:t for t in result.scalars()}
    suffix={"SH":"SS","SZ":"SZ","BJ":"BJ"}
    etfs,etf_version=await asyncio.to_thread(read_cache.document,events.DB_PATH,"etf_universe")
    # 编码完整7300只列表在线程中完成，保留旧数组契约，避免阻塞其他请求。
    def encode():
        from app.cycle.read_cache import response
        rows=[dict(symbol=stock["code"]+"."+suffix[stock["exchange"]],name=stock["name"],market="CN",asset_type=stock.get("asset_type","STOCK"),
            last_synced_at=stored[stock["code"]].last_synced_at.isoformat() if stock["code"] in stored and stored[stock["code"]].last_synced_at else None,
            data_status="stored" if stock["code"] in stored else "按需读取真实日线") for stock in [*universe["stocks"],*(etfs or {}).get("rows",[])]]
        return response(rows,request,("tickers",universe_version,etf_version,tuple(sorted((k,v.last_synced_at.isoformat() if v.last_synced_at else None) for k,v in stored.items()))))
    return await asyncio.to_thread(encode)



@router.get("/{symbol}/prices")
async def get_prices(symbol: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Price.trade_date, Price.open, Price.high, Price.low, Price.close, Price.volume)
        .where(Price.ticker_symbol == symbol)
        .order_by(Price.trade_date)
    )
    rows = result.all()
    if not rows:
        from app.cycle.market import fetch_daily,normalize_symbol
        from app.cycle.all_a import saved
        try:
            code=normalize_symbol(symbol)[2:]
            from app.cycle.etf_universe import is_etf
            if code not in {s["code"] for s in (saved() or {}).get("stocks",[])} and not is_etf(code):
                raise ValueError("证券不在官方股票或ETF母池中")
            frame=await asyncio.to_thread(fetch_daily,symbol,640)
            return frame.rename(columns={"trade_date":"date"}).to_dict("records")
        except Exception as exc:
            raise HTTPException(503,"真实日线不可用："+str(exc)[:120]) from exc
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
