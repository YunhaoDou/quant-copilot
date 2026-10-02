"""Fund-flow signal endpoint: CMF/MFI/OBV-derived money-in/money-out read for a ticker."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services import fund_flow

router = APIRouter(prefix="/fundflow", tags=["fund_flow"])


class FundFlowRequest(BaseModel):
    symbol: str


@router.post("")
async def get_fund_flow(req: FundFlowRequest, session: AsyncSession = Depends(get_session)):
    try:
        return await fund_flow.get_fund_flow_signal(session, req.symbol)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
