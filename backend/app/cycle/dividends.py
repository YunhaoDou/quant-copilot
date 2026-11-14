"""迁移红利看板的公开数据规则；全市场初筛、分类排序与真实历史核验。"""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, date
from pathlib import Path
from statistics import median
from threading import Lock
import copy
import json
import re
import sqlite3
from contextlib import closing

from fastapi import APIRouter, Request

from app.cycle.dividend_quality import screen_candidate
from app.cycle.engine import load_config
from app.cycle.live import number

router = APIRouter(prefix="/dividends", tags=["红利观察"])
DB_PATH = Path(__file__).resolve().parents[2] / "data" / "cycle" / "dividends.sqlite"
_lock = Lock()
_executor = ThreadPoolExecutor(max_workers=1)
_state = {"status":"idle", "progress":"尚未扫描", "stocks":[], "failures":[], "scanned":0, "preselected":0, "checked":0}


def classify(sector):
    for pattern, category in [("银行|保险|证券|多元金融","金融"),("煤炭|油气|石油|炼化|能源金属|燃气","能源资源"),("电力|水务|环保","公用事业"),("铁路|公路|港口|航运|航空|物流|工程建设|建筑装饰|基础建设","交通基建"),("食品|饮料|白酒|啤酒|乳品|家电|汽车|纺织|服装|旅游|酒店|零售|农林牧渔|美容护理","消费制造"),("医药|医疗|生物制品","医药健康"),("电子|计算机|通信|传媒|半导体|软件|互联网","科技通信")]:
        if re.search(pattern, sector):
            return category
    return "工业材料"


def build_dividends(records, as_of):
    cutoff = date.fromisoformat(as_of)-timedelta(days=365)
    grouped = {}
    for row in records:
        code, ex = row.get("SECURITY_CODE"), (row.get("EX_DIVIDEND_DATE") or "")[:10]
        cash = number(row.get("PRETAX_BONUS_RMB"))
        if not code or not ex or cash is None or cash <= 0 or row.get("ASSIGN_PROGRESS") != "实施分配" or ex > as_of:
            continue
        key = (ex, cash, row.get("REPORT_DATE"))
        grouped.setdefault(str(code).zfill(6), {})[key] = row
    result = {}
    for code, unique in grouped.items():
        rows = list(unique.values())
        recent = [r for r in rows if r["EX_DIVIDEND_DATE"][:10] > cutoff.isoformat()]
        total = sum(float(r["PRETAX_BONUS_RMB"])/10 for r in recent)
        years = {int(r["EX_DIVIDEND_DATE"][:4]) for r in rows}
        consecutive, year = 0, max(years)
        while year in years:
            consecutive += 1
            year -= 1
        previous_years = range(int(as_of[:4])-3, int(as_of[:4]))
        yearly = [sum(float(r["PRETAX_BONUS_RMB"])/10 for r in rows if int(r["EX_DIVIDEND_DATE"][:4]) == y) for y in previous_years]
        share_fields = ("BONUS_IT_RATIO", "BONUS_RATIO", "IT_RATIO")
        historical_share_change = any(
            int(r["EX_DIVIDEND_DATE"][:4]) >= previous_years.start
            and any((number(r.get(field)) or 0) > 0 for field in share_fields)
            for r in rows
        )
        fiscal = {}
        final_years = set()
        incomplete_years = set()
        for row in rows:
            period = (row.get("REPORT_DATE") or "")[:10]
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", period):
                continue
            year = int(period[:4])
            if period.endswith("-12-31"):
                final_years.add(year)
            shares = number(row.get("TOTAL_SHARES"))
            if shares is None or shares <= 0:
                incomplete_years.add(year)
                continue
            fiscal[year] = fiscal.get(year, 0) + float(row["PRETAX_BONUS_RMB"])/10*shares
        distributions = {y: amount for y, amount in fiscal.items() if y in final_years and y not in incomplete_years}
        result[code] = dict(fiscalDistributions=distributions, annualCashPerShare=[dict(year=y, cash=value) for y,value in zip(previous_years,yearly)] if not historical_share_change else [], historicalCashPerShare=median(yearly) if all(yearly) and not historical_share_change else None, cashPerShare=total, consecutiveYears=consecutive, shareChange=any((number(r.get(field)) or 0) > 0 for r in recent for field in share_fields), dividendRecords=[dict(exDate=r["EX_DIVIDEND_DATE"][:10], cashPerShare=float(r["PRETAX_BONUS_RMB"])/10, reportDate=(r.get("REPORT_DATE") or "")[:10]) for r in sorted(rows,key=lambda r:r["EX_DIVIDEND_DATE"], reverse=True)[:15]])
    return result


def update(**fields):
    with _lock:
        _state.update(fields)


def scan():
    """共用全A股深入核验；不再先截取红利候选。"""
    try:
        from app.cycle.full_market import scan as full_scan
        payload=full_scan(update)
        DB_PATH.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(DB_PATH)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS board (id INTEGER PRIMARY KEY,payload TEXT NOT NULL)")
            db.execute("INSERT OR REPLACE INTO board VALUES (1,?)",(json.dumps(payload,ensure_ascii=False,allow_nan=False),))
        update(**payload)
    except Exception as exc:
        update(status="error",progress="全A股扫描失败："+str(exc)[:200])


def board():
    with _lock:
        if _state["status"] == "idle" and DB_PATH.exists():
            with closing(sqlite3.connect(DB_PATH)) as db, db:
                row = db.execute("SELECT payload FROM board WHERE id=1").fetchone()
                if row:
                    _state.update(json.loads(row[0]))
        snapshot = copy.deepcopy(_state)
    if snapshot.get("strategyVersion",0)<4:
        snapshot.update(stocks=[],legacy_snapshot=True)
        if snapshot["status"]!="running":snapshot.update(status="needs_refresh",progress="旧快照存在候选数量限制，请重新执行全A股深入核验")
    if snapshot.get("strategyVersion", 0) >= 4:
        config = load_config()
        # 自由现金流的覆盖线与生成财务分层时保持一致。
        config.update({k: v for k, v in snapshot.get("config", {}).items() if k == "dividend_min_fcf_cover"})
        for stock in snapshot["stocks"]:
            stock["screening"] = screen_candidate(stock, snapshot.get("benchmark"), config)
    return snapshot


@router.post("/scan",status_code=202)
def start_scan():
    with _lock:
        if _state["status"] == "running":
            return {"status":"running", "progress":_state["progress"]}
        _state.update(status="running",progress="准备读取真实全市场数据",error=None)
        _executor.submit(scan)
        return {"status":"running", "progress":_state["progress"]}


@router.get("")
def board_http(request:Request):
    from app.cycle.read_api import legacy_dividends
    return legacy_dividends(request)
