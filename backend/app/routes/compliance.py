"""Compliance Q&A endpoint: grounded answers with citations over the internal reference corpus."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.redis_client import redis_client
from app.services import compliance_qa

router = APIRouter(prefix="/compliance", tags=["compliance"])


class ComplianceRequest(BaseModel):
    question: str
    lang: str = "en"


@router.post("")
async def ask_compliance(req: ComplianceRequest):
    try:
        return await compliance_qa.answer_question(redis_client, req.question, lang=req.lang)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
