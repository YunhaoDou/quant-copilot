"""Systematic-simulation read endpoints: standings vs the SPY benchmark + equity curves."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import PaperAccount, SimEquity
from app.services import sim

router = APIRouter(prefix="/sim", tags=["sim"])


@router.get("/report")
async def report(session: AsyncSession = Depends(get_session)):
    """Latest total-return standings for each strategy account vs the SPY benchmark."""
    return await sim.sim_report(session)


@router.get("/curves")
async def curves(session: AsyncSession = Depends(get_session)):
    """Per-account daily equity series, for plotting net-value curves against SPY."""
    accounts = (
        await session.execute(select(PaperAccount).where(PaperAccount.name.like("sim-%")).order_by(PaperAccount.name))
    ).scalars().all()
    out = []
    for acct in accounts:
        rows = (
            await session.execute(
                select(SimEquity.trade_date, SimEquity.equity)
                .where(SimEquity.account_id == acct.id)
                .order_by(SimEquity.trade_date)
            )
        ).all()
        out.append(
            {
                "account": acct.name,
                "series": [{"date": r.trade_date.isoformat(), "equity": round(r.equity, 2)} for r in rows],
            }
        )
    return out
