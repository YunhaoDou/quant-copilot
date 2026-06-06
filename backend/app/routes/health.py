"""Health-check endpoint. Verifies DB and Redis connectivity."""
from fastapi import APIRouter
from redis.asyncio import from_url as redis_from_url
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health():
    """Returns 200 with component statuses. Backend MVP smoke test."""
    db_ok = False
    db_err = None
    try:
        engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        await engine.dispose()
        db_ok = True
    except Exception as e:
        db_err = str(e)

    redis_ok = False
    redis_err = None
    try:
        r = redis_from_url(settings.REDIS_URL)
        await r.ping()
        await r.close()
        redis_ok = True
    except Exception as e:
        redis_err = str(e)

    return {
        "status": "ok" if db_ok and redis_ok else "degraded",
        "components": {
            "database": {"ok": db_ok, "error": db_err},
            "redis": {"ok": redis_ok, "error": redis_err},
        },
    }
