"""官方全A股完整因子排名，共用深入核验任务，未知证券保留。"""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session

router = APIRouter(prefix="/screening", tags=["screening"])


class ScreeningRequest(BaseModel):
    top_n: int | None = None
    refresh: bool = False
    lang: str = "en"


@router.post("")
def run_screening(req: ScreeningRequest):
    from app.cycle.full_market import screening_snapshot
    from app.cycle.dividends import start_scan
    from datetime import datetime
    from app.cycle.live import TZ
    result=screening_snapshot()
    if req.refresh or result.get("trade_date")!=datetime.now(TZ).date().isoformat():
        start_scan()
        result.update(status="running",progress="正在核验完整A股母池")
    return result


@router.get("")
def screening_status(request:Request):
    from app.cycle.read_api import legacy_screening
    return legacy_screening(request)
