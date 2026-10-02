"""FastAPI entry point."""
from contextlib import asynccontextmanager

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
    asset_allocation,
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
    yield


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
)

app.include_router(health.router)
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
app.include_router(asset_allocation.router)
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
