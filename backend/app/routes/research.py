"""LLM research-note endpoint (M2 slice): schema-validated, retried, Redis-cached."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.tasks.backtest_tasks import _run_research, run_research_note_task

router = APIRouter(prefix="/research", tags=["research"])


class ResearchRequest(BaseModel):
    symbol: str
    run_async: bool = False


@router.post("")
async def research(req: ResearchRequest):
    if req.run_async:
        task = run_research_note_task.delay(req.symbol)
        return {"task_id": task.id, "status": "queued"}
    try:
        return await _run_research(req.symbol)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
