"""轻量存活及有界的DB/Redis就绪检查。"""
import asyncio
import os
from datetime import datetime,timezone
from time import monotonic
from fastapi import APIRouter
from redis.asyncio import from_url as redis_from_url
from sqlalchemy import text
from app.config import settings
from app.db.session import engine
_started=monotonic()
_started_at=datetime.now(timezone.utc).isoformat()
router=APIRouter(prefix="/health",tags=["health"])

@router.get("/live")
async def live():return {"status":"alive","pid":os.getpid(),"started_at":_started_at,"uptime_seconds":round(monotonic()-_started,3)}

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


@router.get('/resources')
async def resources():
    """只读资源计数，不返回账户、证券或任何凭据。"""
    from app.cycle import read_cache
    from app.cycle.resources import stats
    from app.cycle.market import cache_stats
    from app.cycle.events import DB_PATH
    wal=DB_PATH.with_name(DB_PATH.name+'-wal')
    try:wal_bytes=wal.stat().st_size
    except FileNotFoundError:wal_bytes=0
    return {'cache':read_cache.cache_stats(),'market_cache':cache_stats(),'market':stats(),'sqlite_wal_bytes':wal_bytes,
            'independent_iopv':{'status':'未授权','enabled':False,'scope':'待授权方案仅覆盖深市，当前未接入','documentation_url':'https://tushare.pro/document/2?doc_id=454'},
            'note':'缓存预算只约束保留缓存，非进程RSS上限；配额只管理公共报价与日线，不改变策略。'}
