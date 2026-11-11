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
