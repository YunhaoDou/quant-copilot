"""Multi-factor screening endpoint: ranks the ingested universe, returns the top N."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services import screening

router = APIRouter(prefix="/screening", tags=["screening"])


class ScreeningRequest(BaseModel):
    top_n: int = 10
    lang: str = "en"


@router.post("")
async def run_screening(req: ScreeningRequest, session: AsyncSession = Depends(get_session)):
    return await screening.run_screening(session, top_n=req.top_n, lang=req.lang, market="CN")
