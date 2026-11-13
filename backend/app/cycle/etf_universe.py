"""沪深全部上市ETF追踪，按官方名单去重；失败和短历史证券保留。"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from io import BytesIO
from threading import Lock
from time import monotonic
import json
import re
import httpx
import numpy as np
import pandas as pd
from fastapi import APIRouter, Query
from app.cycle.events import database, encode
from app.cycle.engine import load_config
from app.cycle.live import TZ
from app.cycle.market import fetch_quotes, fetch_daily
from app.services import indicators

router=APIRouter(prefix="/etfs",tags=["全ETF追踪"])
_executor=ThreadPoolExecutor(max_workers=1)
_lock=Lock()
_state={"status":"idle","progress":"尚未采集ETF", "checked":0,"total":0,"error":None}
_last_attempt=0.
UA="Mozilla/5.0"


def schema(db):
    db.execute("CREATE TABLE IF NOT EXISTS etf_universe (id INTEGER PRIMARY KEY CHECK(id=1),payload TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS etf_evidence (code TEXT PRIMARY KEY,as_of TEXT,payload TEXT)")


def saved():
    with database() as db:
        schema(db);row=db.execute("SELECT payload FROM etf_universe WHERE id=1").fetchone()
    return json.loads(row[0]) if row else None


def official_etfs():
    """上交所FUND_LIST全部00类（含交易型货币），深交所完整Excel中严格只选ETF。"""
    with httpx.Client(trust_env=False,timeout=30,headers={"User-Agent":UA}) as client:
        params={"sqlId":"FUND_LIST","fundType":"00","isPagination":"true","pageHelp.pageSize":10000,"pageHelp.pageNo":1}
        p=client.get("https://query.sse.com.cn/commonSoaQuery.do",params=params,headers={"Referer":"https://www.sse.com.cn/"});p.raise_for_status();d=p.json();raw=d.get("result")
        if not isinstance(raw,list) or len(raw)!=int(d["pageHelp"]["total"]):raise ValueError("上交所ETF名单未完整收齐")
        categories={"01":"股票","03":"股票","09":"股票","31":"股票","08":"跨市场股票","33":"跨境","02":"债券","32":"债券","37":"债券","05":"货币","06":"商品"}
        sh=[dict(code=r["fundCode"],name=r.get("secNameFull") or r["fundAbbr"],exchange="SH",asset_type="ETF",category=categories.get(r.get("subClass"),"其他/待核实"),category_source="上交所基金类别",index_name=r.get("INDEX_NAME") or None,listed_date=str(r.get("listingDate") or ""),manager=r.get("companyName")) for r in raw]
        r=client.get("https://fund.szse.cn/api/report/ShowReport",params={"SHOWTYPE":"xlsx","CATALOGID":"1000_lf","TABKEY":"tab1"});r.raise_for_status()
        frame=pd.read_excel(BytesIO(r.content),dtype={"基金代码":str})
        required={"基金代码","基金简称","基金类别","投资类别"}
        if not required.issubset(frame.columns):raise ValueError("深交所基金名单字段变化")
        source=frame[frame["基金类别"]=="ETF"]
        if source.empty:raise ValueError("深交所ETF名单为空")
        category={"股票基金":"股票","债券基金":"债券","货币市场基金":"货币"}
        sz=[dict(code=str(r["基金代码"]).zfill(6),name=r["基金简称"],exchange="SZ",asset_type="ETF",category=category.get(r["投资类别"],"其他/待核实"),category_source="深交所投资类别；跨境/商品细类待核实",index_name=None,listed_date=str(r.get("上市日期") or ""),manager=r.get("基金管理人")) for r in source.to_dict("records")]
    rows=sh+sz
    if len({r["code"] for r in rows})!=len(rows) or any(not re.fullmatch(r"\d{6}",r["code"]) for r in rows):raise ValueError("ETF名单存在重复或非法代码")
    return sorted(rows,key=lambda r:r["code"])


def history_metrics(frame):
    if frame.empty:raise ValueError("无可用日线")
    c=frame.sort_values("trade_date").close.astype(float)
    if not np.isfinite(c).all() or (c<=0).any():raise ValueError("日线价格不合法")
    def ret(n):return float((c.iloc[-1]/c.iloc[-n-1]-1)*100) if len(c)>n else None
    # volatility60: 60个交易日收益的样本标准差年化后转百分数；max_drawdown: 全历史峰谷回撤（百分数，负值）。
    return dict(history_through=str(frame.trade_date.max()),history_count=len(c),return20=ret(20),return63=ret(63),return252=ret(252),volatility60=float(indicators.annualized_volatility(c.pct_change().dropna().tail(60))*100) if len(c)>60 else None,max_drawdown=float(indicators.max_drawdown(c)*100),ma200=float(c.tail(200).mean()) if len(c)>=200 else None)


def refresh():
    if not _lock.acquire(blocking=False):return
    try:
        now=datetime.now(TZ);today=now.date().isoformat();cfg=load_config();old=saved()
        _state.update(status="running",progress="读取沪深完整ETF名单",error=None,checked=0)
        rows=official_etfs();previous={r["code"]:r for r in (old or {}).get("rows",[])}
        for row in rows:
            row.update({k:v for k,v in previous.get(row["code"],{}).items() if k not in row})
        payload=dict(scope="all-listed-etf",date=today,updated_at=now.isoformat(),source="上交所FUND_LIST完整名单 / 深交所基金完整Excel",total=len(rows),rows=rows,notes=["沪深上市ETF含跨境、债券、货币、商品；不含LOF、REITs及场外联接份额。","类别沿用交易所字段：深交所股票基金可能含跨境ETF，跨境/商品细类尚未完整核验；类别筛选不代表该细类的完整覆盖，全部名单不受影响。","ETF不用公司PE、PB、派息率筛选；历史收益不代表未来；净值/IOPV未取得时保持未知。"])
        with database() as db:schema(db);db.execute("INSERT OR REPLACE INTO etf_universe VALUES(1,?)",(encode(payload),))
        _state.update(total=len(rows),progress="逐只核验ETF真实报价与已完成日线")
        quotes={};errors=[]
        def batch(codes):return fetch_quotes(codes)["quotes"]
        with ThreadPoolExecutor(max_workers=cfg["research_scan_workers"]) as pool:
            jobs={pool.submit(batch,[r["code"] for r in rows[i:i+100]]):i for i in range(0,len(rows),100)}
            for f in as_completed(jobs):
                try:quotes.update({q["code"]:q for q in f.result()})
                except Exception as exc:errors.append(str(exc)[:120])
        bucket=today+(":close" if now.hour>=15 else ":prior")
        with database() as db:cache={r[0]:json.loads(r[1]) for r in db.execute("SELECT code,payload FROM etf_evidence WHERE as_of=?",(bucket,))}
        def collect(row):
            row=dict(row);row["data_errors"]=[];q=quotes.get(row["code"])
            row["quote"]=({**q,"pe":None,"pb":None} if q else None)
            if not q:row["data_errors"].append("报价缺失")
            metrics=cache.get(row["code"])
            if metrics is None:
                try:
                    metrics=history_metrics(fetch_daily(row["code"],cfg["all_stock_history_bars"]))
                    with database() as db:db.execute("INSERT OR REPLACE INTO etf_evidence VALUES(?,?,?)",(row["code"],bucket,encode(metrics)))
                except Exception as exc:row["data_errors"].append("日线："+str(exc)[:100]);metrics={}
            row["metrics"]=metrics;row["status"]="ready" if q and metrics else "unknown"
            return row
        output=[]
        with ThreadPoolExecutor(max_workers=cfg["research_scan_workers"]) as pool:
            for i,f in enumerate(as_completed([pool.submit(collect,r) for r in rows]),1):
                output.append(f.result());_state.update(checked=i,progress=f"全ETF深入核验 {i}/{len(rows)}")
        payload.update(rows=sorted(output,key=lambda r:r["code"]),updated_at=datetime.now(TZ).isoformat(),errors=errors,checked=len(output),ready=sum(r["status"]=="ready" for r in output))
        with database() as db:db.execute("INSERT OR REPLACE INTO etf_universe VALUES(1,?)",(encode(payload),))
        _state.update(status="ready",progress="全ETF核验完成",checked=len(output))
    except Exception as exc:_state.update(status="error",error=str(exc)[:250],progress="ETF采集失败，保留已有名单与证据")
    finally:_lock.release()


def enqueue(force=False):
    global _last_attempt
    cfg=load_config()
    if _state["status"]=="running" or (not force and monotonic()-_last_attempt<cfg["etf_refresh_seconds"]):return
    _last_attempt=monotonic();_state.update(status="running",progress="ETF采集已排队");_executor.submit(refresh)


def is_etf(code):return any(r["code"]==code for r in (saved() or {}).get("rows",[]))


@router.get("")
def listing(page:int=Query(1,ge=1),page_size:int=Query(50,ge=1,le=200),query:str="",category:str="全部"):
    from app.cycle import events,read_cache
    p,_=read_cache.document(events.DB_PATH,"etf_universe")
    p=p or {"rows":[],"total":0,"source":"等待官方名单","notes":[]}
    rows=[r for r in p["rows"] if (not query or query in r["code"] or query in r["name"]) and (category=="全部" or r["category"]==category)]
    progress=dict(_state)
    if progress["status"]=="idle" and p["rows"]:progress.update(status="saved",progress="已载入持久化ETF快照，等待后台更新",checked=p.get("checked",0),total=p["total"])
    return {**{k:v for k,v in p.items() if k!="rows"},"categories":sorted({r["category"] for r in p["rows"]}),"refresh_seconds":load_config()["etf_refresh_seconds"],"progress":progress,"matched":len(rows),"page":page,"page_size":page_size,"rows":rows[(page-1)*page_size:page*page_size]}


@router.post("/refresh",status_code=202)
def request_refresh():enqueue(True);return dict(_state)
