"""迁移红利看板的公开数据规则；全市场初筛、分类排序与真实历史核验。"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, date
from pathlib import Path
from statistics import median
from threading import Lock
import copy
import json
import math
import re
import sqlite3

from fastapi import APIRouter
import httpx

from app.cycle.dividend_benchmark import fetch_benchmark
from app.cycle.dividend_quality import annual_statements, assess_quality, quality_order
from app.cycle.engine import load_config
from app.cycle.live import TZ, number
from app.cycle.market import fetch_daily

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


def get_json(client, url, params):
    response = client.get(url, params=params)
    response.raise_for_status()
    return response.json()


def paginate(client, url, params, page_name, size, config, kind):
    def fetch(page):
        payload = get_json(client, url, {**params,page_name:page})
        if kind == "market":
            data = payload.get("data")
            if not data:
                raise ValueError("全A股数据源未返回有效列表")
            rows = data.get("diff", [])
            return list(rows.values()) if isinstance(rows,dict) else rows, int(data["total"])
        result = payload.get("result")
        if not payload.get("success") or not result:
            raise ValueError("分红接口："+str(payload.get("message", "无数据")))
        return result.get("data", []), int(result["count"])
    rows, total = fetch(1)
    pages = math.ceil(total/size)
    if pages > config["dividend_max_pages"]:
        raise ValueError("数据源分页超过配置上限，未使用截断数据冒充全市场")
    with ThreadPoolExecutor(max_workers=config["dividend_workers"]) as pool:
        futures = [pool.submit(fetch,p) for p in range(2,pages+1)]
        for future in as_completed(futures):
            page_rows, page_total = future.result()
            if page_total != total:
                raise ValueError("扫描期间数据总数变化，请重试完整扫描")
            rows.extend(page_rows)
            update(progress=f"正在读取{'全A股列表' if kind == 'market' else '已实施分红'} {len(rows)}/{total}")
    if len(rows) != total:
        raise ValueError("分页未完整返回，停止扫描")
    return rows


def scan():
    config = load_config()
    failures = []
    try:
        with httpx.Client(trust_env=False,timeout=config["live_timeout_seconds"],headers={"Referer":"https://quote.eastmoney.com/","User-Agent":"Mozilla/5.0"}) as client:
            market = paginate(client,"https://push2.eastmoney.com/api/qt/clist/get",dict(pz=config["dividend_market_page_size"],po=1,np=1,fltt=2,fid="f12",fs="m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",fields="f12,f13,f14,f2,f20,f100,f124,f9,f23"),"pn",config["dividend_market_page_size"],config,"market")
            if len({r["f12"] for r in market}) != len(market):
                raise ValueError("全市场列表含重复代码，不能确认扫描完整性")
            timestamps = [datetime.fromtimestamp(r["f124"],TZ) for r in market if number(r.get("f124"))]
            if not timestamps:
                raise ValueError("行情源缺少时间戳")
            as_of = max(timestamps).date().isoformat()
            start = date.fromisoformat(as_of)-timedelta(days=366*config["dividend_lookback_years"])
            records = paginate(client,"https://datacenter-web.eastmoney.com/api/data/v1/get",dict(reportName="RPT_SHAREBONUS_DET",columns="SECURITY_CODE,SECURITY_NAME_ABBR,ASSIGN_PROGRESS,EX_DIVIDEND_DATE,PRETAX_BONUS_RMB,REPORT_DATE,BONUS_IT_RATIO,BONUS_RATIO,IT_RATIO,TOTAL_SHARES",sortColumns="EX_DIVIDEND_DATE",sortTypes="-1",pageSize=config["dividend_page_size"],source="WEB",client="WEB",filter=f'(ASSIGN_PROGRESS="实施分配")(EX_DIVIDEND_DATE>=\'{start.isoformat()}\')(EX_DIVIDEND_DATE<=\'{as_of}\')'),"pageNumber",config["dividend_page_size"],config,"dividend")
        dividends = build_dividends(records, as_of)
        preliminary = []
        for row in market:
            code, price, cap = str(row["f12"]), number(row.get("f2")), number(row.get("f20"))
            d = dividends.get(code)
            stamp = datetime.fromtimestamp(row["f124"],TZ) if number(row.get("f124")) else None
            if not d or not price or not cap or cap < config["dividend_min_market_cap"] or re.search(r"ST|退|^N",row["f14"]) or not stamp or stamp.date().isoformat() != as_of:
                continue
            yield_pct = d["cashPerShare"]/price*100
            if yield_pct < config["dividend_min_yield_pct"] or d["consecutiveYears"] < config["dividend_min_years"]:
                continue
            if d["shareChange"]:
                failures.append(code+"：近12个月存在送转，待核实每股分红口径，暂不参与排名")
                continue
            sector = row.get("f100") or "待分类"
            preliminary.append(dict(code=code,name=row["f14"],price=price,marketCap=cap,sector=sector,category=classify(sector),dividendYield=yield_pct,quoteTime=stamp.isoformat(),pe=number(row.get("f9")),pb=number(row.get("f23")),**d))
        preliminary.sort(key=lambda r:(-(r["historicalCashPerShare"] or 0)/r["price"], -r["consecutiveYears"], -r["dividendYield"], r["code"]))
        candidates = preliminary[:config["dividend_max_deep_check"]]
        update(scanned=len(market),preselected=len(preliminary),checked=0,progress=f"正在核验{len(candidates)}只候选的真实年报")
        with httpx.Client(trust_env=False, timeout=config["live_timeout_seconds"], headers={"User-Agent":"Mozilla/5.0"}) as client:
            try:
                benchmark = fetch_benchmark(client, as_of)
            except (httpx.HTTPError, ValueError) as exc:
                benchmark = None
                failures.append(f"十年期国债收益率不可用：{str(exc)[:100]}")
            statements, report_errors = annual_statements(client, [s["code"] for s in candidates], as_of, config)
        failures.extend(report_errors)
        def enrich(stock):
            history = fetch_daily(stock["code"],config["dividend_history_bars"])
            values = history.close.astype(float).tolist()
            if len(values) < config["dividend_min_history_bars"]:
                raise ValueError("日线不足配置要求")
            low,high = min(values),max(values)
            position = max(0,min(100,(stock["price"]-low)/(high-low)*100)) if high != low else 50
            stock.update(history=values,historyDates=history.trade_date.tolist(),historyThrough=history.trade_date.max(),lowPosition=round(position,1),drawdown=round((stock["price"]/high-1)*100,2),signal="stage" if position <= config["dividend_low_position_pct"] else "wait" if position >= config["dividend_high_position_pct"] else "watch")
            stock["quality"] = assess_quality(stock, statements, config)
            del stock["fiscalDistributions"]
            return stock
        stocks = []
        with ThreadPoolExecutor(max_workers=config["dividend_workers"]) as pool:
            futures = {pool.submit(enrich,dict(stock)):stock["code"] for stock in candidates}
            for index,future in enumerate(as_completed(futures),1):
                try:
                    stocks.append(future.result())
                except Exception as exc:
                    failures.append(futures[future]+"："+str(exc)[:100])
                update(checked=index,progress=f"日线核验 {index}/{len(candidates)}")
        if candidates and not stocks:
            raise ValueError("候选日线全部核验失败，未生成模拟排名")
        payload = dict(status="ready",progress="真实数据扫描完成",tradeDate=as_of,updatedAt=datetime.now(TZ).isoformat(),stocks=sorted(stocks,key=quality_order),strategyVersion=3,benchmark=benchmark,scanned=len(market),preselected=len(preliminary),checked=len(candidates),failures=failures,source="东方财富全A股报价/已实施分红/年报摘要 + 腾讯前复权日线",config=config,
            notes=["近12月股息率=过去365天已实施税前每股现金分红/扫描报价；每10股派现已除以10。", "连续派息按除权年份、自最近派息年回溯，最多验证配置窗口；不是未来分红承诺。", "送转导致每股口径不可直接比较的标的已排除，特殊分红和可持续性需复核公告。", "全市场初筛后最多核验配置数量的候选，分类前8仅在已核验候选中排名；并非完整全市场最优。", "先按财务分层排序，层内按历史中位股息率、连续派息年数、近12月息率排列。价格位置不参与排名。", "历史中位股息率用前三个完整除权年度每股派息中位数除以扫描价。派息率用同财年已实施派息估算额除以归母净利，自由现金流覆盖用经营现金流减购建长期资产现金支出后除以该估算额。", "派息总额按每股派息乘供应商股本估算，A/H或差异化分红需核对公告。仅使用扫描日已可见年报。金融股另查资本充足或偿付能力。控制人、第一大股东、未分配利润与分红政策查公司公告。"])
        DB_PATH.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(DB_PATH) as db:
            db.execute("CREATE TABLE IF NOT EXISTS board (id INTEGER PRIMARY KEY,payload TEXT NOT NULL)")
            db.execute("INSERT OR REPLACE INTO board VALUES (1,?)",(json.dumps(payload,ensure_ascii=False,allow_nan=False),))
        update(**payload)
    except Exception as exc:
        update(status="error",progress="扫描失败："+str(exc)[:200],failures=failures)


@router.get("")
def board():
    with _lock:
        if _state["status"] == "idle" and DB_PATH.exists():
            with sqlite3.connect(DB_PATH) as db:
                row = db.execute("SELECT payload FROM board WHERE id=1").fetchone()
                if row:
                    _state.update(json.loads(row[0]))
        return copy.deepcopy(_state)


@router.post("/scan",status_code=202)
def start_scan():
    with _lock:
        if _state["status"] == "running":
            return {"status":"running", "progress":_state["progress"]}
        _state.update(status="running",progress="准备读取真实全市场数据",error=None)
        _executor.submit(scan)
        return {"status":"running", "progress":_state["progress"]}
