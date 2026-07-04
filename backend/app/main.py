"""FastAPI entry point."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app import __version__
from app.config import settings
from app.db.init_db import init_models
from app.db.session import AsyncSessionLocal
from app.models import Strategy
from app.routes import backtest, health, research, tickers
from app.services.strategies import STRATEGIES


async def _seed_strategies() -> None:
    async with AsyncSessionLocal() as session:
        existing = {s.key for s in (await session.execute(select(Strategy))).scalars()}
        for key, spec in STRATEGIES.items():
            if key not in existing:
                session.add(Strategy(key=key, name=spec["label"], default_params=spec["default_params"]))
        await session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_models()
    await _seed_strategies()
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


@app.get("/")
def root():
    return {
        "name": "quant-copilot",
        "version": __version__,
        "environment": settings.ENVIRONMENT,
        "docs": "/docs",
    }
