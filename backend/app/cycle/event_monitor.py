"""后端运行期间在采集窗口持续跟踪事件。"""
import asyncio
from datetime import datetime
import logging
import json
import sqlite3

from app.cycle.engine import load_config
from app.cycle.live import TZ, DB_PATH, live_dashboard
from app.cycle.events import ingest

logger = logging.getLogger(__name__)
monitor_status = {"state": "启动中", "last_success": None, "error": None}

def restore_captures():
    """接续当日已存快照，历史截取的梯队明确标注覆盖范围。"""
    if not DB_PATH.exists():
        return
    today = datetime.now(TZ).date().isoformat()
    with sqlite3.connect(DB_PATH) as db:
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='snapshot_details'").fetchone()
        if not exists:
            return
        rows = db.execute("""SELECT s.payload,d.payload FROM snapshots s JOIN snapshot_details d
            ON s.observed_at=d.observed_at WHERE substr(s.observed_at,1,10)=? ORDER BY s.observed_at""", (today,)).fetchall()
    for snapshot, details in rows:
        snapshot, details = json.loads(snapshot), json.loads(details)
        ingest(snapshot, details.get("metadata", {}), snapshot.get("sectors", []),
               snapshot.get("leaders", []), leader_scope="历史全市场前12候选截取")

async def run_monitor():
    try:
        await asyncio.to_thread(restore_captures)
    except Exception:
        logger.exception("已存板块快照接续失败")
    while True:
        config = load_config()
        now = datetime.now(TZ)
        in_window = now.weekday() < 5 and (
            "09:25" <= now.strftime("%H:%M") <= "11:35" or "12:55" <= now.strftime("%H:%M") <= "15:05"
        )
        if in_window:
            try:
                result = await asyncio.to_thread(live_dashboard, config)
                try:
                    from app.cycle.trend_forward import capture
                    await asyncio.to_thread(capture, result)
                except Exception:
                    logger.exception("第七策略证据采集失败，保留原策略更新")
                from app.cycle.strategy_sim import run_simulation
                await asyncio.to_thread(run_simulation)
                metadata = result.get("metadata", {})
                quote = metadata.get("quote_time") or ""
                monitor_status.update(
                    state="事件保存失败" if metadata.get("event_error") else
                        "采集中" if quote[:10] == now.date().isoformat() and not metadata.get("stale") else "等待新鲜行情",
                    last_success=metadata.get("fetched_at"), error=None,
                )
            except Exception as exc:
                logger.warning("板块事件采集失败：%s", exc)
                monitor_status.update(state="采集失败", error="公开行情请求失败，稍后自动重试")
        else:
            monitor_status.update(state="采集窗口外")
        await asyncio.sleep(config["event_poll_seconds"])


async def run_etf_monitor():
    """ETF与月频模拟独立驻留，避免被全股票深入核验拖延到错过收盘。"""
    while True:
        config=load_config()
        try:
            from app.cycle.etf_universe import enqueue
            enqueue()
        except Exception:
            logger.exception("全ETF追踪调度失败")
        try:
            from app.cycle.shibor_sim import run_once
            await asyncio.to_thread(run_once)
        except Exception:
            logger.exception("SHIBOR模拟本轮更新失败")
        await asyncio.sleep(config["event_poll_seconds"])


async def run_account_monitor():
    """账户与报价轮次独立于板块采集，避免供应商慢请求层层串行。"""
    while True:
        config=load_config()
        try:
            from app.cycle.strategy_center import run_accounts
            await asyncio.to_thread(run_accounts)
        except Exception:
            logger.exception("研究策略账户本轮更新失败")
        try:
            from app.cycle.trend_forward import run_forward
            await asyncio.to_thread(run_forward)
        except Exception:
            logger.exception("第七策略账户本轮更新失败")
        await asyncio.sleep(config["event_poll_seconds"])


async def run_read_model_monitor():
    """后台预热只读快照；失败保留旧版本，不触碰账户或补造数据。"""
    from app.cycle.read_api import dividend_model,screening_model
    while True:
        for build in (dividend_model,screening_model):
            try:await asyncio.to_thread(build)
            except Exception:logger.exception("只读快照预热失败，下一轮重试")
        await asyncio.sleep(5)
