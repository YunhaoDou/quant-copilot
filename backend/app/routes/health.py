"""轻量存活及有界的DB/Redis就绪检查。"""
import asyncio
from fastapi import APIRouter
from redis.asyncio import from_url as redis_from_url
from sqlalchemy import text
from app.config import settings
from app.db.session import engine
router=APIRouter(prefix="/health",tags=["health"])

@router.get("/live")
async def live():return {"status":"alive"}

@router.get("")
async def health():
    async def database():
        try:
            async with engine.connect() as c:await c.execute(text("SELECT 1"))
            return {"ok":True,"error":None}
        except Exception as exc:return {"ok":False,"error":str(exc)}
    async def redis():
        client=redis_from_url(settings.REDIS_URL,socket_connect_timeout=2,socket_timeout=2)
        try:await client.ping();return {"ok":True,"error":None}
        except Exception as exc:return {"ok":False,"error":str(exc)}
        finally:await client.aclose()
    async def bounded(fn):
        try:return await asyncio.wait_for(fn(),timeout=3)
        except asyncio.TimeoutError:return {"ok":False,"error":"健康检查超过3秒"}
    db,r=await asyncio.gather(bounded(database),bounded(redis))
    return {"status":"ok" if db["ok"] and r["ok"] else "degraded","components":{"database":db,"redis":r}}
