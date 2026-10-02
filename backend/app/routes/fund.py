"""A-share fund endpoints: ingest NAV/price history, list funds, fetch history, analysis."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Fund, FundNav
from app.services import fund_analysis, fund_data

router = APIRouter(prefix="/funds", tags=["funds"])


@router.post("/{code}/ingest")
async def ingest(code: str, start: str = "20230101", session: AsyncSession = Depends(get_session)):
    try:
        count = await fund_data.ingest_fund(session, code, start=start)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ingestion failed: {exc}") from exc
    if count == 0:
        raise HTTPException(status_code=404, detail="no data returned for this fund code")
    return {"code": code, "rows_upserted": count}


@router.get("")
async def list_funds(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Fund))
    return [
        {"code": f.code, "name": f.name, "fund_type": f.fund_type, "last_synced_at": f.last_synced_at}
        for f in result.scalars()
    ]


@router.get("/{code}/nav")
async def get_nav_history(code: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(FundNav.nav_date, FundNav.nav, FundNav.acc_nav, FundNav.close)
        .where(FundNav.fund_code == code)
        .order_by(FundNav.nav_date)
    )
    rows = result.all()
    if not rows:
        raise HTTPException(status_code=404, detail="no NAV data ingested for this fund yet")
    return [
        {"date": r.nav_date.isoformat(), "nav": r.nav, "acc_nav": r.acc_nav, "close": r.close} for r in rows
    ]


@router.get("/{code}/analysis")
async def get_analysis(code: str, session: AsyncSession = Depends(get_session)):
    fund = (await session.execute(select(Fund).where(Fund.code == code))).scalar_one_or_none()
    if fund is None:
        raise HTTPException(status_code=404, detail="fund not found — ingest it first")
    return await fund_analysis.get_fund_analysis(session, code, fund.fund_type)
