"""M5 risk-panel endpoint: exposure / concentration / drawdown for a paper account."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services import risk
from app.services.paper_trading import OrderError

router = APIRouter(prefix="/risk", tags=["risk"])


@router.get("/accounts/{account_id}")
async def account_risk(account_id: int, session: AsyncSession = Depends(get_session)):
    try:
        return await risk.risk_snapshot(session, account_id)
    except OrderError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
