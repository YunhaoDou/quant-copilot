"""FastAPI entry point."""
from contextlib import asynccontextmanager, suppress
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app import __version__
from app.config import settings
from app.db.init_db import init_models
from app.db.session import AsyncSessionLocal
from app.models import Strategy, Ticker
from app.routes import app_settings as app_settings_route
from app.routes import (
    backtest,
    compliance,
    fund as fund_route,
    fund_flow,
    health,
    news_sentiment,
    paper,
    research,
    risk,
    screening,
    sim,
    tickers,
)
from app.services import app_settings as app_settings_service
from app.services.strategies import STRATEGIES
from app.cycle.api import router as cycle_router
from app.cycle.market import router as market_router
from app.cycle.dividends import router as dividend_router
from app.routes.research_lab import router as research_lab_router
from app.cycle.radar import router as radar_router
from app.cycle.companies import router as companies_router
from app.cycle.events import router as events_router
from app.cycle.event_monitor import run_monitor, run_etf_monitor, run_account_monitor, run_read_model_monitor
from app.cycle.strategy_sim import router as strategy_sim_router
from app.cycle.trend_forward import router as trend_forward_router
from app.cycle.trend_leader import router as trend_leader_router
from app.cycle.strategy_center import router as strategy_center_router

# A-share starter universe. Yahoo Finance uses .SS/.SZ suffixes for mainland listings.
A_SHARE_UNIVERSE = {
    "600519.SS": "贵州茅台",
    "000858.SZ": "五粮液",
    "601318.SS": "中国平安",
    "600036.SS": "招商银行",
    "000333.SZ": "美的集团",
    "300750.SZ": "宁德时代",
    "002594.SZ": "比亚迪",
    "600900.SS": "长江电力",
    "601668.SS": "中国建筑",
    "510300.SS": "沪深300ETF",
}


async def _seed_strategies() -> None:
    async with AsyncSessionLocal() as session:
        existing = {s.key for s in (await session.execute(select(Strategy))).scalars()}
        for key, spec in STRATEGIES.items():
            if key not in existing:
                session.add(Strategy(key=key, name=spec["label"], default_params=spec["default_params"]))
        await session.commit()


async def _seed_tickers() -> None:
    async with AsyncSessionLocal() as session:
        existing = {t.symbol for t in (await session.execute(select(Ticker))).scalars()}
        for symbol, name in A_SHARE_UNIVERSE.items():
            if symbol not in existing:
                session.add(Ticker(symbol=symbol, name=name, market="CN"))
        await session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_models()
    await _seed_strategies()
    await _seed_tickers()
    async with AsyncSessionLocal() as session:
        await app_settings_service.load_settings_from_db(session)
    event_task = asyncio.create_task(run_monitor())
    etf_task = asyncio.create_task(run_etf_monitor())
    account_task = asyncio.create_task(run_account_monitor())
    read_task = asyncio.create_task(run_read_model_monitor())
    try:
        yield
    finally:
        event_task.cancel()
        etf_task.cancel()
        account_task.cancel()
        read_task.cancel()
        for task in (event_task,etf_task,account_task,read_task):
            with suppress(asyncio.CancelledError):
                await task


app = FastAPI(
    title="Quant Copilot API",
    version=__version__,
    description="AI-powered quant research platform — backend",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["ETag"],
)

from app.cycle.etf_universe import router as etf_router
from app.cycle.shibor_sim import router as shibor_router
from app.cycle.read_api import router as read_router
app.include_router(read_router)
app.include_router(etf_router)
app.include_router(shibor_router)
app.include_router(health.router)
app.include_router(strategy_center_router)
app.include_router(trend_leader_router)
app.include_router(trend_forward_router)
app.include_router(strategy_sim_router)
app.include_router(events_router)
app.include_router(cycle_router)
app.include_router(market_router)
app.include_router(dividend_router)
app.include_router(research_lab_router)
app.include_router(radar_router)
app.include_router(companies_router)
app.include_router(tickers.router)
app.include_router(backtest.router)
app.include_router(research.router)
app.include_router(news_sentiment.router)
app.include_router(compliance.router)
app.include_router(paper.router)
app.include_router(risk.router)
app.include_router(fund_flow.router)
app.include_router(fund_route.router)
app.include_router(screening.router)
app.include_router(sim.router)
app.include_router(app_settings_route.router)


@app.get("/")
def root():
    return {
        "name": "quant-copilot",
        "version": __version__,
        "environment": settings.ENVIRONMENT,
        "docs": "/docs",
    }
