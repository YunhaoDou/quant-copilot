"""第七策略：严格证据的独立前向模拟；复用保守撮合，不回填成交。"""
from datetime import datetime
import json
from threading import Lock
from fastapi import APIRouter, HTTPException
from app.cycle.events import database, encode
from app.cycle.live import TZ
from app.cycle.engine import load_config
from app.cycle.strategy_sim import new_account, step, log
from app.cycle.trend_leader import evaluate_live, BASE

router = APIRouter(prefix="/trend-forward", tags=["第七策略前向模拟"])
_lock = Lock()


def schema(db):
    db.execute("CREATE TABLE IF NOT EXISTS trend_forward_account (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS trend_forward_captures (stamp TEXT PRIMARY KEY, payload TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS trend_forward_symbols (symbol TEXT PRIMARY KEY)")


def read(db):
    schema(db)
    row = db.execute("SELECT payload FROM trend_forward_account WHERE id=1").fetchone()
    return json.loads(row[0]) if row else None


def save(db, account):
    db.execute("INSERT OR REPLACE INTO trend_forward_account VALUES(1,?)",(encode(account),))


def track(symbol):
    from app.cycle.market import normalize_symbol
    code = normalize_symbol(symbol)[2:]
    with database() as db:
        schema(db)
        db.execute("INSERT OR IGNORE INTO trend_forward_symbols VALUES(?)",(code,))


def capture(result):
    """采集当时已公开的完整板块/涨停池；旧截取数据不冒充完整历史。"""
    evidence = result.get("current",{}).get("trend_evidence")
    meta = result.get("metadata",{})
    stamp = meta.get("quote_time")
    now = datetime.now(TZ)
    if not evidence or not stamp:
        return
    age = (now-datetime.fromisoformat(stamp)).total_seconds()
    if stamp[:10] != now.date().isoformat() or not 0 <= age <= load_config()["live_stale_seconds"]:
        return
    with database() as db:
        schema(db)
        db.execute("INSERT OR IGNORE INTO trend_forward_captures VALUES(?,?)",(stamp,encode({"metadata":meta,"evidence":evidence})))
        for row in evidence.get("leaders",[]):
            db.execute("INSERT OR IGNORE INTO trend_forward_symbols VALUES(?)",(row["symbol"],))


def advance(account, package, now, config):
    """只接收判定后的后续新鲜报价；账户单仓，不套用旧策略的固定止盈。"""
    quote, result = package["quote"], package["result"]
    stamp = quote["quote_time"]
    age = (now-datetime.fromisoformat(stamp)).total_seconds()
    clock = now.strftime("%H:%M")
    in_session = now.weekday() < 5 and ("09:30" <= clock <= "11:30" or "13:00" <= clock <= "15:00")
    if not in_session or stamp[:10] != now.date().isoformat() or not 0 <= age <= config["live_stale_seconds"]:
        return
    code = quote["code"]
    cap = result["position_cap_pct"]
    held = account.get("position")
    if not held and not account.get("pending"):
        account["rules"]["position_pct"] = cap
    # 入场上限在每个新报价重新核验，不沿用已消失的条件。
    if account.get("pending",{} ) and account["pending"]["side"] == "buy":
        account["rules"]["position_pct"] = min(account["rules"]["position_pct"],cap)
    event_id = "trend-forward:"+code
    event = {"id":event_id,"status":"active","stage":"","dates":[],
        "entry_key":code+":"+stamp[:10],"signal_reason":"第七策略五环证据全部满足",
        "first":{"market":{}},"latest":{
            "quote_time":stamp,"observed_at":package["source"].get("evaluated_at",package["source"]["fetched_at"]),
            "market":{"risk":"关注"},"sector":{"started":result["decision"] == "BUY_CANDIDATE"},
            "exit_failed":result["decision"] in ("EXIT","REDUCE"),
            "leaders":[{"symbol":code}],"watched":[{"symbol":code,"quote":quote}]}}
    # 趋势策略减仓信号首版保守退出全部单仓，单独披露，不伪称按比例减仓。
    old = account.get("position")
    step(account,[event],policy="trend")
    if not old and account.get("position"):
        p = account["position"]
        cfg = json.loads((BASE/"config.json").read_text())
        p["stop_loss_price"] = p["entry_price"]*(1-cfg["position"]["stop_loss_pct"])
        p["entry_audit_id"] = result["audit_log_id"]


def run_forward():
    if not _lock.acquire(blocking=False):
        return
    try:
        with database() as db:
            account = read(db)
            if not account or account["status"] != "running":
                return
            cfg = json.loads((BASE/"config.json").read_text())
            all_symbols = [row[0] for row in db.execute("SELECT symbol FROM trend_forward_symbols ORDER BY symbol")]
        required = [(account.get(k) or {}).get("symbol") for k in ("position","pending")]
        cursor = account.get("scan_cursor",0)
        count = cfg["simulation"]["symbols_per_cycle"]
        if isinstance(count,bool) or not isinstance(count,int) or not 1 <= count <= 100:
            raise ValueError("simulation.symbols_per_cycle 需为1至100的整数")
        rotated = all_symbols[cursor:]+all_symbols[:cursor]
        symbols = list(dict.fromkeys([s for s in required if s]+rotated[:count]))
        packages, failures = [], []
        for symbol in symbols:
            try:
                packages.append(evaluate_live(symbol, account=account))
            except Exception as exc:
                failures.append(symbol+"："+str(exc)[:120])
        now = datetime.now(TZ)
        with database() as db:
            db.execute("BEGIN IMMEDIATE")
            current = read(db)
            if not current or current["status"] != "running":
                return
            current["scan_cursor"] = (cursor+count)%max(1,len(all_symbols))
            for package in packages:
                advance(current, package, now, load_config())
            current["observations"] = [{"code":p["quote"]["code"],"name":p["quote"]["name"],
                "time":p["quote"]["quote_time"],"decision":p["result"]["decision"],
                "missing":p["missing_evidence"],"reasons":p["result"]["reasons"],
                "audit_id":p["result"]["audit_log_id"]} for p in packages]
            current["last_checked"] = now.isoformat()
            current["failures"] = failures
            log(current,now.isoformat(),f"本轮核验{len(packages)}只；证据不足不建仓，休市或旧报价不成交")
            save(db,current)
    finally:
        _lock.release()


@router.get("")
def status():
    with database() as db:
        account = read(db)
        rows = db.execute("SELECT stamp FROM trend_forward_captures ORDER BY stamp").fetchall()
        count = db.execute("SELECT count(*) FROM trend_forward_symbols").fetchone()[0]
    return {"account":account,"capture_count":len(rows),"capture_dates":sorted({r[0][:10] for r in rows}),
        "symbols":count,"scope":"已采集完整涨停池中的标的及页面查询跟踪标的；不是全市场扫描",
        "limitations":["主线多日证据与资金共振未核验时保持等待；不以涨幅代替资金性质", "REDUCE首版按单仓全部退出，尚未实现分批减仓", "沿用T+1、整手、滑点及涨跌停限制；未模拟盘口排队", "不复权日线遇除权不连续时需复核，不声称已处理公司行为"]}


@router.post("/{action}")
def control(action: str):
    if action not in ("start","pause","exit"):
        raise HTTPException(404,"动作不存在")
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        account = read(db)
        if not account:
            config = load_config()
            cfg = json.loads((BASE/"config.json").read_text())
            config["sim_stop_loss_pct"] = cfg["position"]["stop_loss_pct"]*100
            account = new_account(config)
        if action == "exit":
            p = account["position"]
            account["pending"] = dict(side="sell",symbol=p["symbol"],event_id=p["event_id"],
                signal_time=datetime.now(TZ).isoformat(),reason="人工请求第七策略模拟退出") if p else None
            account["status"] = "running"
        else:
            account["status"] = "running" if action == "start" else "paused"
        log(account,datetime.now(TZ).isoformat(),"第七策略："+action+"；仅模拟，不接券商")
        save(db,account)
    return status()
