"""Backtest endpoints (M3): 4-strategy comparison + parameter sweep."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.session import AsyncSessionLocal
from app.services import backtest_engine, data_ingestion
from app.tasks.backtest_tasks import _run_comparison, run_backtest_comparison_task
from app.tasks.celery_app import celery_app

router = APIRouter(prefix="/backtest", tags=["backtest"])


class CompareRequest(BaseModel):
    symbol: str
    start: str | None = None
    end: str | None = None
    run_async: bool = False


@router.post("/compare")
async def compare(req: CompareRequest):
    if req.run_async:
        task = run_backtest_comparison_task.delay(req.symbol, req.start, req.end)
        return {"task_id": task.id, "status": "queued"}
    try:
        results = await _run_comparison(req.symbol, req.start, req.end)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"symbol": req.symbol, "results": results}


class SweepRequest(BaseModel):
    symbol: str
    strategy_key: str
    param_grid: dict[str, list]


@router.post("/sweep")
async def sweep(req: SweepRequest):
    async with AsyncSessionLocal() as session:
        close = await data_ingestion.load_price_series(session, req.symbol)
    if close.empty:
        raise HTTPException(status_code=404, detail="no price data ingested for this symbol yet")
    try:
        results = backtest_engine.run_param_sweep(close, req.strategy_key, req.param_grid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"symbol": req.symbol, "strategy_key": req.strategy_key, "results": results}


@router.get("/task/{task_id}")
async def task_status(task_id: str):
    result = celery_app.AsyncResult(task_id)
    return {"task_id": task_id, "state": result.state, "result": result.result if result.ready() else None}
