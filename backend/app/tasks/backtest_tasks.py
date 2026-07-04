"""Celery tasks: backtests and LLM research calls run as background jobs, not inline
with the HTTP request. Each task creates its own short-lived async engine (NullPool)
because asyncio.run() tears down its event loop when the task ends, and pooled asyncpg
connections can't survive across event loops.
"""
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models import BacktestCurve, BacktestRun, LLMCall, ResearchNote
from app.redis_client import redis_client
from app.services import backtest_engine, data_ingestion, llm_research
from app.tasks.celery_app import celery_app


def _task_session_factory():
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, future=True)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _run_comparison(symbol: str, start: str | None = None, end: str | None = None) -> list[dict]:
    engine, session_factory = _task_session_factory()
    try:
        async with session_factory() as session:
            close = await data_ingestion.load_price_series(session, symbol)
            if close.empty:
                raise ValueError(f"no price data ingested for {symbol} yet")
            if start:
                close = close[close.index >= start]
            if end:
                close = close[close.index <= end]

            results = backtest_engine.run_comparison(close)
            for r in results:
                run = BacktestRun(
                    ticker_symbol=symbol,
                    strategy_key=r["strategy_key"],
                    params=r["params"],
                    start_date=close.index.min().date(),
                    end_date=close.index.max().date(),
                    total_return=r["total_return"],
                    sharpe_ratio=r["sharpe_ratio"],
                    max_drawdown=r["max_drawdown"],
                    win_rate=r["win_rate"],
                    num_trades=r["num_trades"],
                )
                session.add(run)
                await session.flush()
                curve = r["equity_curve"]
                session.add_all(
                    BacktestCurve(backtest_run_id=run.id, trade_date=d.date(), equity=float(v))
                    for d, v in curve.items()
                )
                r["backtest_run_id"] = run.id
                r["equity_curve"] = {d.strftime("%Y-%m-%d"): float(v) for d, v in curve.items()}
            await session.commit()
            return results
    finally:
        await engine.dispose()


@celery_app.task(name="run_backtest_comparison")
def run_backtest_comparison_task(symbol: str, start: str | None = None, end: str | None = None) -> list[dict]:
    return asyncio.run(_run_comparison(symbol, start, end))


async def _run_research(symbol: str) -> dict:
    engine, session_factory = _task_session_factory()
    try:
        note = await llm_research.get_research_note(redis_client, symbol)
        async with session_factory() as session:
            existing = await session.execute(select(ResearchNote).where(ResearchNote.ticker_symbol == symbol))
            if existing.scalars().first() is None or not note.get("cache_hit"):
                session.add(
                    ResearchNote(
                        ticker_symbol=symbol,
                        thesis=note["thesis"],
                        catalysts=note["catalysts"],
                        risks=note["risks"],
                        fair_value_low=note["fair_value_low"],
                        fair_value_high=note["fair_value_high"],
                        model=note["model"],
                    )
                )
            session.add(
                LLMCall(
                    ticker_symbol=symbol,
                    model=note["model"],
                    purpose="research_note",
                    input_tokens=note.get("input_tokens", 0),
                    output_tokens=note.get("output_tokens", 0),
                    cache_hit=note.get("cache_hit", False),
                    retries=note.get("retries", 0),
                )
            )
            await session.commit()
        return note
    finally:
        await engine.dispose()


@celery_app.task(name="run_research_note")
def run_research_note_task(symbol: str) -> dict:
    return asyncio.run(_run_research(symbol))
