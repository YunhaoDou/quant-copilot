"""FastAPI entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import settings
from app.routes import health

app = FastAPI(
    title="Quant Copilot API",
    version=__version__,
    description="AI-powered quant research platform — backend",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)


@app.get("/")
def root():
    return {
        "name": "quant-copilot",
        "version": __version__,
        "environment": settings.ENVIRONMENT,
        "docs": "/docs",
    }
