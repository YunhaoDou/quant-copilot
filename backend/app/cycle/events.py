"""板块启动事件与后续证据，独立于人工判断和成交记录。"""
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import json
import sqlite3
import uuid
from threading import Lock

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Literal

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "cycle" / "events.sqlite"
router = APIRouter(prefix="/cycle/events", tags=["板块事件跟踪"])


_schema_lock=Lock()
_initialized=set()

@contextmanager
def database(path=None):
    path = path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=15) as db:
        db.row_factory = sqlite3.Row
        identity=(str(path.resolve()),path.stat().st_ino)
        if identity not in _initialized:
            with _schema_lock:
                if identity not in _initialized:
                    try:db.execute("PRAGMA journal_mode=WAL")
                    except sqlite3.OperationalError:pass
                    db.execute("""CREATE TABLE IF NOT EXISTS events (
                        id TEXT PRIMARY KEY, sector_code TEXT NOT NULL, name TEXT NOT NULL,
                        start_date TEXT NOT NULL, first_at TEXT NOT NULL, first_snapshot TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'active', stage TEXT NOT NULL DEFAULT '待确认',
                        plan TEXT NOT NULL DEFAULT '', invalidation TEXT NOT NULL DEFAULT '',
                        UNIQUE(sector_code,start_date))""")
                    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_active_sector ON events(sector_code) WHERE status='active'")
                    db.execute("""CREATE TABLE IF NOT EXISTS observations (
                        event_id TEXT NOT NULL, quote_time TEXT NOT NULL, observed_at TEXT NOT NULL,
                        trade_date TEXT NOT NULL, payload TEXT NOT NULL,
                        PRIMARY KEY(event_id,quote_time))""")
                    db.execute("""CREATE TABLE IF NOT EXISTS records (
                        id TEXT PRIMARY KEY, event_id TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL)""")
                    db.execute("""CREATE TABLE IF NOT EXISTS candidates (
                        event_id TEXT NOT NULL, symbol TEXT NOT NULL, name TEXT NOT NULL,
                        PRIMARY KEY(event_id,symbol))""")
                    _initialized.add(identity)
        yield db


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def ingest(snapshot, metadata, sectors, leaders, path=None, leader_scope="完整涨停池匹配", max_age=180):
    """只接收新鲜同日公开行情，首次条件满足的采集快照保持不变。"""
    quote_time, observed_at = metadata.get("quote_time"), metadata.get("fetched_at")
    if not quote_time or not observed_at:
        return
    quote = datetime.fromisoformat(quote_time)
    fetched = datetime.fromisoformat(observed_at)
    if quote.tzinfo is None or fetched.tzinfo is None:
        return
    age = (fetched - quote).total_seconds()
    if quote.date() != fetched.date() or quote_time[:10] != snapshot.get("date") or not 0 <= age <= max_age:
        return
    if not ("09:25" <= quote_time[11:16] <= "11:35" or "12:55" <= quote_time[11:16] <= "15:05"):
        return
    pools = metadata.get("feeds", {})
    leaders_known = pools.get("涨停池", {}).get("status") == "正常"
    broken_known = pools.get("炸板池", {}).get("status") == "正常"
    with database(path) as db:
        for sector in sectors:
            code = sector.get("code")
            if not code:
                continue
            active = db.execute("SELECT * FROM events WHERE sector_code=? AND status='active'", (code,)).fetchone()
            payload = {
                "sector": sector, "market": {k: snapshot.get(k) for k in
                    ("market_pct", "limit_up", "limit_down", "break_rate", "yesterday_pct", "new_low", "risk")},
                "leaders": [row for row in leaders if row.get("sector") == sector["name"]] if leaders_known else None,
                "broken": [row for row in snapshot.get("broken_leaders", []) if row.get("sector") == sector["name"]] if broken_known else None,
                "quote_time": quote_time, "observed_at": observed_at, "rule_version": snapshot.get("rule_version"),
                "leader_scope": leader_scope,
            }
            if active is None and sector.get("started") is True:
                event_id = str(uuid.uuid4())
                db.execute("""INSERT OR IGNORE INTO events
                    (id,sector_code,name,start_date,first_at,first_snapshot) VALUES(?,?,?,?,?,?)""",
                    (event_id, code, sector["name"], snapshot["date"], observed_at, encode(payload)))
                active = db.execute("SELECT * FROM events WHERE sector_code=? AND status='active'", (code,)).fetchone()
            if active is None:
                continue
            for row in (payload["leaders"] or []) + (payload["broken"] or []):
                db.execute("INSERT OR IGNORE INTO candidates VALUES(?,?,?)", (active["id"], row["symbol"], row["name"]))
            watched = db.execute("SELECT symbol,name FROM candidates WHERE event_id=? ORDER BY symbol", (active["id"],)).fetchall()
            quotes = {row["code"]: row for row in snapshot.get("candidate_quotes", [])}
            payload["watched"] = [
                {"symbol": row["symbol"], "name": row["name"], "quote": quotes.get(row["symbol"])}
                for row in watched
            ]
            latest = db.execute("SELECT quote_time FROM observations WHERE event_id=? ORDER BY quote_time DESC LIMIT 1", (active["id"],)).fetchone()
            if latest and latest["quote_time"] >= quote_time:
                continue
            db.execute("INSERT OR IGNORE INTO observations VALUES(?,?,?,?,?)",
                       (active["id"], quote_time, observed_at, snapshot["date"], encode(payload)))


def tracked_symbols(path=None):
    with database(path) as db:
        return [row[0] for row in db.execute("""SELECT DISTINCT c.symbol FROM candidates c
            JOIN events e ON e.id=c.event_id WHERE e.status='active' ORDER BY c.symbol""")]


def evidence(latest, first, previous=None):
    sector = latest["sector"]
    checks = sector.get("checks", {})
    if not checks or any(value is None for value in checks.values()):
        state = "数据不足"
    elif latest["market"].get("risk") == "高":
        state = "市场风险升高"
    elif not sector.get("started"):
        state = "启动条件已消失"
    elif previous and previous["sector"].get("started") is False:
        state = "启动条件重新满足"
    else:
        state = "启动条件维持"
    def delta(key):
        a, b = sector.get(key), first["sector"].get(key)
        return a-b if a is not None and b is not None else None
    return {"state": state, "pct_change": delta("pct"), "limit_up_change": delta("limit_up")}


def list_events(path=None):
    with database(path) as db:
        rows = db.execute("SELECT * FROM events ORDER BY first_at DESC").fetchall()
        result = []
        for row in rows:
            current = db.execute("SELECT payload,quote_time FROM observations WHERE event_id=? ORDER BY quote_time DESC LIMIT 2", (row["id"],)).fetchall()
            first = json.loads(row["first_snapshot"])
            latest = json.loads(current[0]["payload"]) if current else first
            previous = json.loads(current[1]["payload"]) if len(current) > 1 else None
            dates = [r[0] for r in db.execute("SELECT DISTINCT trade_date FROM observations WHERE event_id=? ORDER BY trade_date", (row["id"],))]
            result.append({k: row[k] for k in ("id", "sector_code", "name", "start_date", "first_at", "status", "stage", "plan", "invalidation")} | {
                "first": first, "latest": latest, "dates": dates, "evidence": evidence(latest, first, previous),
            })
        return result


def detail(event_id, path=None):
    found = next((event for event in list_events(path) if event["id"] == event_id), None)
    if found is None:
        raise HTTPException(404, "事件不存在")
    with database(path) as db:
        rows = db.execute("SELECT observed_at,payload FROM observations WHERE event_id=? ORDER BY quote_time DESC LIMIT 120", (event_id,)).fetchall()
        notes = db.execute("SELECT created_at,payload FROM records WHERE event_id=? ORDER BY created_at DESC", (event_id,)).fetchall()
    return found | {
        "history": [{"observed_at": row["observed_at"], **json.loads(row["payload"])} for row in reversed(rows)],
        "records": [{"created_at": row["created_at"], **json.loads(row["payload"])} for row in notes],
    }


class Plan(BaseModel):
    stage: Literal["待确认", "启动观察", "延续观察", "分歧观察", "回补待确认", "回补确认", "退潮回避", "轮动观察"]
    plan: str = Field(max_length=4000)
    invalidation: str = Field(max_length=2000)
    status: Literal["active", "closed"] = "active"


class Record(BaseModel):
    id: uuid.UUID
    kind: Literal["观察", "人工确认", "未成交", "模拟成交", "实际成交"]
    action: Literal["观察", "买入", "加仓", "减仓", "卖出", "放弃"]
    symbol: str = Field(default="", pattern=r"^(\d{6})?$")
    text: str = Field(min_length=1, max_length=4000)
    price: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    quantity: int | None = Field(default=None, gt=0)


@router.get("")
def events():
    from app.cycle.event_monitor import monitor_status
    return {"events": list_events(), "monitor": dict(monitor_status)}


@router.get("/{event_id}")
def get_event(event_id: str):
    return detail(event_id)


@router.patch("/{event_id}")
def update_plan(event_id: str, body: Plan):
    from app.cycle.live import TZ
    with database() as db:
        old = db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        if not old:
            raise HTTPException(404, "事件不存在")
        if body.status == "closed" and db.execute("SELECT 1 FROM sqlite_master WHERE name='strategy_sim'").fetchone():
            simulation = db.execute("SELECT payload FROM strategy_sim WHERE id=1").fetchone()
            account = json.loads(simulation["payload"]) if simulation else {}
            if any((account.get(key) or {}).get("event_id") == event_id for key in ("position", "pending")):
                raise HTTPException(409, "该事件有模拟持仓或挂单，请先在策略模拟请求退出并等待处理")
        try:
            db.execute("UPDATE events SET stage=?,plan=?,invalidation=?,status=? WHERE id=?",
                       (body.stage, body.plan, body.invalidation, body.status, event_id))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "该板块已有其他进行中的事件")
        # 人工判断留痕，不修改首次快照和自动证据。
        db.execute("INSERT INTO records VALUES(?,?,?,?)",
                   (str(uuid.uuid4()), event_id, datetime.now(TZ).isoformat(),
                    encode({"kind": "人工确认", "action": "观察", "text": f"阶段：{body.stage}\n计划：{body.plan}\n失效条件：{body.invalidation}\n状态：{body.status}"})))
    return detail(event_id)


@router.post("/{event_id}/records")
def add_record(event_id: str, body: Record):
    from app.cycle.live import TZ
    if not body.text.strip():
        raise HTTPException(422, "请填写证据或执行说明")
    if body.kind in ("实际成交", "模拟成交") and (not body.symbol or body.price is None or body.quantity is None):
        raise HTTPException(422, "成交记录需要股票代码、成交价和股数")
    if body.kind in ("实际成交", "模拟成交") and body.action not in ("买入", "加仓", "减仓", "卖出"):
        raise HTTPException(422, "成交记录请选择买入、加仓、减仓或卖出")
    with database() as db:
        if not db.execute("SELECT 1 FROM events WHERE id=?", (event_id,)).fetchone():
            raise HTTPException(404, "事件不存在")
        payload = body.model_dump(mode="json")
        existing = db.execute("SELECT event_id,payload FROM records WHERE id=?", (str(body.id),)).fetchone()
        if existing and (existing["event_id"] != event_id or json.loads(existing["payload"]) != payload):
            raise HTTPException(409, "记录标识重复，请刷新后重试")
        db.execute("INSERT OR IGNORE INTO records VALUES(?,?,?,?)",
                   (str(body.id), event_id, datetime.now(TZ).isoformat(), encode(payload)))
    return detail(event_id)
