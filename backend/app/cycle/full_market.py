"""全A股共用深入核验：每只普通A股都有结果，缺失不删除，不取前N名。"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from threading import Lock
import copy
import json
import numpy as np
import pandas as pd
from app.cycle.events import database, encode
from app.cycle.live import TZ
from app.cycle.resources import background_task
from app.cycle.engine import load_config
from app.cycle.market import fetch_daily, fetch_quotes

_lock=Lock()
state={"status":"idle","progress":"尚未进行全A股深入核验","scanned":0,"checked":0,"failures":[],"stocks":[]}


def schema(db):
    db.execute("CREATE TABLE IF NOT EXISTS full_stock_bars (code TEXT PRIMARY KEY,bucket TEXT,payload TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS full_stock_screening (id INTEGER PRIMARY KEY CHECK(id=1),payload TEXT)")


def scan(update):
    """由红利扫描后台任务调度；原始日线同日复用，结果逐股可追溯。"""
    if not _lock.acquire(blocking=False):raise ValueError("全A股深入核验已在运行")
    try:
        from app.cycle import all_a
        from app.cycle.dividend_quality import screen_candidate
        from app.services.screening import compute_stock_factors,rank_universe
        cfg=load_config();now=datetime.now(TZ);today=now.date().isoformat()
        universe=all_a.saved()
        update(status="running",progress="读取官方全A股名单与财务证据",scanned=(universe or {}).get("total",0),checked=0)
        if not universe or universe.get("tradeDate")!=today or universe.get("schema_version",0)<2:
            universe=all_a.refresh()
        stocks=copy.deepcopy(universe["stocks"]);total=len(stocks)
        bucket=today+":"+str(cfg["all_stock_history_bars"])+":qfq"+(":close" if now.strftime("%H:%M")>="15:00" else ":prior")
        state.update(status="running",progress="读取全A股报价与日线",scanned=total,checked=0,failures=[])
        update(status="running",progress=state["progress"],scanned=total,checked=0)
        with database() as db:
            schema(db)
            cached={r[0]:json.loads(r[1]) for r in db.execute("SELECT code,payload FROM full_stock_bars WHERE bucket=?",(bucket,))}
        quotes={};failures=[]
        codes=[s["code"] for s in stocks]
        @background_task
        def quote_batch(batch):return fetch_quotes(batch)["quotes"]
        with ThreadPoolExecutor(max_workers=cfg["research_scan_workers"]) as pool:
            tasks={pool.submit(quote_batch,codes[n:n+100]):codes[n:n+100] for n in range(0,total,100)}
            for f in as_completed(tasks):
                try:quotes.update({q["code"]:q for q in f.result()})
                except Exception as exc:failures.append("报价批次"+tasks[f][0]+"："+str(exc)[:100])
        factors=[];output=[]
        @background_task
        def collect(stock):
            code=stock["code"];errors=[]
            raw=cached.get(code)
            if raw is None:
                try:
                    frame=fetch_daily(code,cfg["all_stock_history_bars"])
                    if frame.empty:raise ValueError("无日线")
                    if not np.isfinite(frame.close).all() or (frame.close<=0).any():raise ValueError("日线价格不合法")
                    raw=frame.to_dict("records")
                    with database() as db:db.execute("INSERT OR REPLACE INTO full_stock_bars VALUES(?,?,?)",(code,bucket,encode(raw)))
                except Exception as exc:raw=[];errors.append("日线："+str(exc)[:100])
            frame=pd.DataFrame(raw)
            quote=quotes.get(code)
            stock.update(history=[],historyDates=[],historyThrough=None,historyLow=None,historyHigh=None,
                lowPosition=None,drawdown=None,signal="unknown",price=None,dividendYield=None,quoteTime=None)
            if quote and quote.get("price",0)>0:
                stock.update(price=quote["price"],quoteTime=quote["quote_time"],pe=quote.get("pe"),pb=quote.get("pb"))
                stock["dividendYield"]=stock["cashPerShare"]/stock["price"]*100
            else:errors.append("报价缺失，估值与股息率保持未知")
            factor=None
            if len(raw):
                frame=frame.sort_values("trade_date")
                prices=frame.close.astype(float)
                stock.update(historyThrough=str(frame.trade_date.iloc[-1]),historyLow=float(prices.min()),historyHigh=float(prices.max()))
                if stock["price"] is not None:
                    low,high=stock["historyLow"],stock["historyHigh"]
                    pos=max(0,min(100,(stock["price"]-low)/(high-low)*100)) if high!=low else 50
                    stock.update(lowPosition=pos,drawdown=(stock["price"]/high-1)*100,signal="stage" if pos<=cfg["dividend_low_position_pct"] else "wait" if pos>=cfg["dividend_high_position_pct"] else "watch")
                if len(raw)<cfg["dividend_min_history_bars"]:errors.append("历史短于红利价格位置参考窗口")
                if len(raw)>=20:
                    try:
                        analysis=frame.set_index(pd.DatetimeIndex(frame.trade_date))
                        factor=compute_stock_factors(analysis,code)
                        factor.values={k:v if v is None or np.isfinite(v) else None for k,v in factor.values.items()}
                    except Exception as exc:errors.append("因子："+str(exc)[:100])
                else:errors.append("不足20根日线，因子保持未知")
            stock.setdefault("dividendRecords",[]);stock.setdefault("annualCashPerShare",[])
            baseline=stock.get("historicalCashPerShare");quality=stock.get("quality") or {}
            quality["historicalYield"]=baseline/stock["price"]*100 if baseline and stock["price"] else None
            stock["quality"]=quality
            stock["screening"]=screen_candidate(stock,universe.get("benchmark"),cfg)
            stock["dataErrors"]=errors;stock["historyCount"]=len(raw)
            return stock,factor,errors
        with ThreadPoolExecutor(max_workers=cfg["research_scan_workers"]) as pool:
            tasks={pool.submit(collect,s):s["code"] for s in stocks}
            for i,f in enumerate(as_completed(tasks),1):
                stock,factor,errors=f.result();output.append(stock)
                if factor:factors.append(factor)
                failures.extend(stock["code"]+"："+e for e in errors)
                state.update(checked=i,progress=f"全A股深入核验 {i}/{total}")
                update(checked=i,progress=state["progress"])
        ranked=rank_universe(factors,lang="zh")
        ranked_codes={r["symbol"] for r in ranked}
        names={s["code"]:s["name"] for s in output}
        screening_rows=[{**r,"name":names[r["symbol"]],"status":"scored","as_of_date":str(r["as_of_date"].date())} for r in ranked]
        screening_rows.extend(dict(symbol=s["code"],name=s["name"],rank=None,composite_score=None,factors={},reasons=s["dataErrors"] or ["数据不足"],as_of_date=s["historyThrough"],status="unknown") for s in output if s["code"] not in ranked_codes)
        stamp=datetime.now(TZ).isoformat()
        with database() as db:db.execute("INSERT OR REPLACE INTO full_stock_screening VALUES(1,?)",(encode(dict(results=screening_rows,universe_size=total,scored=len(ranked),unknown=total-len(ranked),scope="all-a",status="ready",updated_at=stamp,trade_date=today)),))
        payload=dict(status="ready",scope="all-a",progress="全A股深入核验完成",tradeDate=today,updatedAt=stamp,
            stocks=sorted(output,key=lambda s:(s.get("quality",{}).get("status")!="supported",-(s.get("dividendYield") or 0),s["code"])),
            scanned=total,checked=total,preselected=sum(s["screening"]["status"]=="pass" for s in output),
            strategyVersion=4,benchmark=universe.get("benchmark"),failures=failures,source=universe["source"]+" / 腾讯报价与前复权日线",config=cfg,
            notes=["官方普通A股名单全部纳入，每只都进行财务、分红、报价与日线核验；无前N只或分类名额截断。", "无分红、ST、停牌及日线不足证券保留在母池，按证据显示未达标或未知；不补造缺失数据。", "价格位置使用前复权历史与现价比较，跨除权仍需复核；股息率为已实施税前分红口径。", "个股排行不是下单建议；展示分页不缩小后台扫描范围。"])
        state.update(status="ready",progress=payload["progress"],checked=total,scanned=total)
        return payload
    except Exception as exc:
        state.update(status="error",progress="全A股深入核验失败",error=str(exc)[:180]);raise
    finally:_lock.release()


def screening_snapshot():
    with database() as db:
        schema(db);row=db.execute("SELECT payload FROM full_stock_screening WHERE id=1").fetchone()
    if row:return json.loads(row[0])
    from app.cycle.all_a import saved
    universe=saved()
    return dict(results=[],universe_size=(universe or {}).get("total",0),scored=0,unknown=(universe or {}).get("total",0),scope="all-a",status=state["status"],progress=state["progress"])
