"""第八策略：隔夜SHIBOR月频ETF轮动的独立前向账本；无券商接口。"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from threading import Lock
import json
import re
import httpx
import numpy as np
import pandas as pd
from fastapi import APIRouter,HTTPException
from app.cycle.events import database,encode
from app.cycle.engine import load_config
from app.cycle.live import TZ
from app.cycle.market import fetch_quotes,fetch_daily

router=APIRouter(prefix="/shibor-sim",tags=["SHIBOR ETF前向模拟"])
_lock=Lock()
_run_lock=Lock()
_executor=ThreadPoolExecutor(max_workers=1)
_runtime={"state":"等待启动","error":None,"updated_at":None}


def schema(db):
    db.execute("CREATE TABLE IF NOT EXISTS shibor_sim (id INTEGER PRIMARY KEY CHECK(id=1),payload TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS shibor_feed (key TEXT PRIMARY KEY,payload TEXT NOT NULL)")


def read(db):
    schema(db);row=db.execute("SELECT payload FROM shibor_sim WHERE id=1").fetchone()
    return json.loads(row[0]) if row else None


def save(db,a):db.execute("INSERT OR REPLACE INTO shibor_sim VALUES(1,?)",(encode(a),))


def cached(key):
    with database() as db:
        schema(db);row=db.execute("SELECT payload FROM shibor_feed WHERE key=?",(key,)).fetchone()
    return json.loads(row[0]) if row else None


def store(key,payload):
    with database() as db:schema(db);db.execute("INSERT OR REPLACE INTO shibor_feed VALUES(?,?)",(key,encode(payload)))


def rates(now):
    bucket=now.date().isoformat()+(":am" if now.hour<11 else ":pm")
    old=cached("overnight")
    if old and old.get("bucket")==bucket:return old
    params={"reportName":"RPT_IMP_INTRESTRATEN","columns":"REPORT_DATE,IR_RATE","filter":'(MARKET_CODE="001")(CURRENCY_CODE="CNY")(INDICATOR_ID="001")',"pageSize":500,"sortTypes":"-1","sortColumns":"REPORT_DATE"}
    with httpx.Client(trust_env=False,timeout=25) as client:
        def page(n):
            r=client.get("https://datacenter-web.eastmoney.com/api/data/v1/get",params={**params,"pageNumber":n});r.raise_for_status();d=r.json().get("result")
            if not d:raise ValueError("SHIBOR源没有完整数据")
            return d
        first=page(1)
        with ThreadPoolExecutor(max_workers=4) as pool:other=list(pool.map(page,range(2,first["pages"]+1)))
    all_pages=[first,*other]
    if any(x["count"]!=first["count"] for x in all_pages):raise ValueError("SHIBOR分页总数变化")
    raw=[r for d in all_pages for r in d["data"]]
    if len(raw)!=first["count"] or len({r["REPORT_DATE"] for r in raw})!=len(raw):raise ValueError("SHIBOR分页未完整收齐或日期重复")
    cutoff=now.date().isoformat() if now.hour>=11 else (now.date()-timedelta(days=1)).isoformat()
    rows=sorted([{"date":r["REPORT_DATE"][:10],"rate":float(r["IR_RATE"])} for r in raw if r["REPORT_DATE"][:10]<=cutoff],key=lambda r:r["date"])
    if not rows or any(not np.isfinite(r["rate"]) or not 0<=r["rate"]<=100 for r in rows):raise ValueError("SHIBOR数据不合法")
    payload=dict(bucket=bucket,rows=rows,source="东方财富转引SHIBOR隔夜报价；非政策利率",observed_at=now.isoformat(),last_date=rows[-1]["date"])
    store("overnight",payload);return payload


def signal(rows,as_of,rules):
    visible=[r for r in rows if r["date"]<=as_of]
    if not visible:raise ValueError("该月末没有可得SHIBOR")
    s=pd.Series([r["rate"] for r in visible],index=pd.to_datetime([r["date"] for r in visible])).sort_index()
    if s.index.has_duplicates:raise ValueError("利率日期重复")
    if (pd.Timestamp(as_of)-s.index[-1]).days>21:raise ValueError("月末利率证据过旧")
    smooth=s.rolling(rules["smoothing_quotes"]).mean();rank=smooth.rolling(rules["history_quotes"]).rank(pct=True).iloc[-1]
    if not np.isfinite(rank):raise ValueError("SHIBOR历史不足，禁止补造信号")
    growth=bool(rank<=rules["low_percentile"])
    return dict(as_of=as_of,rate_date=str(s.index[-1].date()),rate=float(s.iloc[-1]),smooth_rate=float(smooth.iloc[-1]),percentile=float(rank),dividend_weight=0. if growth else 1.,growth_weight=1. if growth else 0.,reason="隔夜利率5日均值处于过去756报价日低25%分位，偏向成长" if growth else "隔夜利率分位高于25%，偏向红利")


def actions(code,now):
    key="actions:"+code;old=cached(key)
    if old and old["date"]==now.date().isoformat():return old["events"]
    with httpx.Client(trust_env=False,timeout=20) as client:
        r=client.get(f"https://fund.eastmoney.com/pingzhongdata/{code}.js");r.raise_for_status()
    m=re.search(r"var\s+Data_netWorthTrend\s*=\s*(\[.*?\]);",r.text)
    if not m:raise ValueError("基金分红/拆分数据缺失")
    events=[]
    for r in json.loads(m.group(1)):
        if not r.get("unitMoney"):continue
        date=datetime.fromtimestamp(r["x"]/1000,TZ).date().isoformat();events.append(dict(date=date,text=r["unitMoney"]))
    store(key,dict(date=now.date().isoformat(),events=events));return events


def new_account(now,cfg):
    rules=dict(version="shibor-on-v1",history_quotes=cfg["shibor_history_quotes"],smoothing_quotes=cfg["shibor_smoothing_quotes"],low_percentile=cfg["shibor_low_percentile"],dividend_code=cfg["shibor_dividend_code"],growth_code=cfg["shibor_growth_code"],cost_bps=cfg["shibor_cost_bps"],slippage_bps=cfg["shibor_slippage_bps"],min_commission=cfg["shibor_min_commission"],limit_pct=cfg["shibor_limit_pct"],lot_size=100,drawdown_pause_pct=cfg["sim_drawdown_limit_pct"],initial_dividend_pct=cfg["shibor_initial_dividend_pct"])
    capital=cfg["initial_capital"];stamp=now.isoformat()
    return dict(status="running",created_at=stamp,review_date=(now.date()+timedelta(days=182)).isoformat(),capital=capital,cash=capital,equity=capital,peak=capital,positions={},position=None,pending=dict(kind="initial",created_at=stamp,dividend_weight=rules["initial_dividend_pct"]/100,growth_weight=1-rules["initial_dividend_pct"]/100,reason="初始各半，等待启动后新鲜可成交报价"),last_month=now.strftime("%Y-%m"),trades=[],decisions=[],curve=[],processed={},corporate_actions=[],rules=rules,signal=None,risk_exit=False,fees=0.)


def log(a,now,text):
    if not a["decisions"] or a["decisions"][-1]["text"]!=text:a["decisions"].append(dict(time=now.isoformat(),text=text))


def apply_actions(a,events_by_code,now):
    for code,events in events_by_code.items():
        for event in events:
            if not a["created_at"][:10]<=event["date"]<=now.date().isoformat():continue
            key=code+":"+event["date"]+":"+event["text"]
            if key in a["corporate_actions"]:continue
            p=a["positions"].get(code)
            if p and p["buy_date"]<event["date"]:
                match=re.search(r"每份.*?现金\s*([0-9.]+)",event["text"])
                if not match:raise ValueError("持仓发生未识别分红/拆分，暂停撮合等待核实："+code+event["text"])
                cash=float(match.group(1))*p["quantity"];a["cash"]+=cash;log(a,now,f"{code}已披露现金分红入账{cash:.2f}元")
            a["corporate_actions"].append(key)


def fresh(q,now,created_at=None):
    if not q or not q.get("price") or q["price"]<=0 or not q.get("previous_close") or q.get("volume_lots",0)<=0:return False
    try:t=datetime.fromisoformat(q["quote_time"])
    except (KeyError,ValueError):return False
    return t.date()==now.date() and 0<=(now-t).total_seconds()<=load_config()["live_stale_seconds"] and (not created_at or t>datetime.fromisoformat(created_at))


def mark(a,quotes,now):
    for code,p in a["positions"].items():
        q=quotes.get(code)
        if q and q.get("price",0)>0 and q["quote_time"]>=p.get("mark_time","") and q["quote_time"]<=now.isoformat():p.update(mark=q["price"],mark_time=q["quote_time"])
    a["equity"]=a["cash"]+sum(p["quantity"]*p["mark"] for p in a["positions"].values());a["peak"]=max(a["peak"],a["equity"])
    point=dict(date=now.date().isoformat(),equity=a["equity"],time=now.isoformat())
    if a["curve"] and a["curve"][-1]["date"]==point["date"]:a["curve"][-1]=point
    else:a["curve"].append(point)


def tick(value):return float(Decimal(str(value)).quantize(Decimal(".001"),rounding=ROUND_HALF_UP))


def execute(a,quotes,now):
    plan=a["pending"]
    if not plan:return
    rules=a["rules"];codes=[rules["dividend_code"],rules["growth_code"]]
    weights=[plan["dividend_weight"],plan["growth_weight"]]
    needed=[c for c,w in zip(codes,weights) if w>0 or c in a["positions"]]
    if not all(fresh(quotes.get(c),now,plan["created_at"]) for c in needed):log(a,now,"等待相关ETF启动/决策之后的新鲜有效报价，旧报价不成交");return
    stamp=max((quotes[c]["quote_time"] for c in needed),default=now.isoformat())
    if stamp<=a["processed"].get(plan["id"] if "id" in plan else plan["kind"],""):return
    a["processed"][plan.get("id",plan["kind"])]=stamp
    mark(a,quotes,now)
    budget=a["equity"]/(1+rules["cost_bps"]/10000)
    desired={code:int(budget*weight/quotes[code]["price"]/(1+rules["slippage_bps"]/10000)//100)*100 if weight>0 else 0 for code,weight in zip(codes,weights)}
    blocked=False
    for side in ["sell","buy"]:
        for code in codes:
            p=a["positions"].get(code);held=p["quantity"] if p else 0;diff=desired[code]-held
            if (side=="sell" and diff>=0) or (side=="buy" and diff<=0):continue
            q=quotes[code]
            if side=="sell" and p["buy_date"]>=now.date().isoformat():blocked=True;log(a,now,"T+1约束：当日买入份额不可卖出");continue
            pct=rules["limit_pct"][code]/100
            upper,lower=tick(q["previous_close"]*(1+pct)),tick(q["previous_close"]*(1-pct))
            if side=="buy" and q["price"]>=upper-.0001 or side=="sell" and q["price"]<=lower+.0001:blocked=True;log(a,now,f"{code}触及涨跌停，保守视为无法{side}");continue
            if side=="buy" and blocked:continue
            price=tick(q["price"]*(1+(1 if side=="buy" else -1)*rules["slippage_bps"]/10000));price=min(upper,max(lower,price))
            quantity=abs(diff);cost=lambda n:max(rules["min_commission"],n*price*rules["cost_bps"]/10000)
            if side=="buy":
                while quantity and quantity*price+cost(quantity)>a["cash"]+1e-8:quantity-=100
                if not quantity:continue
            fee=cost(quantity);pnl=None
            if side=="sell":
                proceeds=quantity*price-fee;a["cash"]+=proceeds;pnl=quantity*(price-p["cost_price"])-fee;p["quantity"]-=quantity
                if not p["quantity"]:del a["positions"][code]
            else:
                a["cash"]-=quantity*price+fee
                total=held+quantity;basis=((p["cost_price"]*held if p else 0)+quantity*price+fee)/total
                a["positions"][code]=dict(symbol=code,name=q["name"],quantity=total,cost_price=basis,buy_date=now.date().isoformat(),mark=q["price"],mark_time=q["quote_time"])
            a["fees"]+=fee;a["trades"].append(dict(time=q["quote_time"],recorded_at=now.isoformat(),symbol=code,name=q["name"],side=side,price=price,quantity=quantity,fee=fee,pnl=pnl,reason=plan["reason"],plan_id=plan.get("id",plan["kind"]),universe_scope="ETF固定双标的"))
    if not blocked:
        a["pending"]=None;log(a,now,"本轮模拟调整已执行，剩余现金来自整手、费用及滑点约束")
        if a["risk_exit"]:
            a["status"]="risk_paused" if a.get("risk_triggered") else "paused"
            if not a.get("risk_triggered"):a["risk_exit"]=False
    mark(a,quotes,now)
    if a["cash"]<-.001:raise ValueError("现金约束异常，拒绝保存")


def step(a,quotes,now,feed,calendar):
    mark(a,quotes,now)
    if a["status"]!="running":return a
    if (1-a["equity"]/a["peak"])*100>=a["rules"]["drawdown_pause_pct"] and not a["risk_exit"]:
        a["risk_exit"]=True;a["risk_triggered"]=True;a["pending"]=dict(kind="risk",created_at=now.isoformat(),dividend_weight=0.,growth_weight=0.,reason="20%回撤防线触发，等待可成交报价退出并暂停")
    month=now.strftime("%Y-%m")
    if not a["risk_exit"] and month>a["last_month"] and not a["pending"]:
        cutoff=(now.replace(day=1)-timedelta(days=1)).date().isoformat();s=signal(feed["rows"],cutoff,a["rules"]);a["signal"]=s
        a["pending"]=dict(kind="monthly",id=month,month=month,created_at=now.isoformat(),**s)
        a["last_month"]=month;log(a,now,"已冻结月末信号，等待次月首个交易日收盘；不回填错过的成交")
    clock=now.strftime("%H:%M");in_session=now.weekday()<5 and ("09:30"<=clock<="11:30" or "13:00"<=clock<"15:00")
    plan=a["pending"]
    if not plan:return a
    if plan["kind"]=="monthly":
        days=sorted(d for d in calendar if d.startswith(month))
        if days and days[0]<now.date().isoformat():log(a,now,"错过当月首个交易日收盘，跳过该月，不使用历史价格补单");a["pending"]=None;return a
        if not days or days[0]!=now.date().isoformat() or not "15:00"<=clock<="15:05":return a
        # 必须在收盘之前已有决策，不能看到收盘后才创建并成交。
        if plan["created_at"]>=now.date().isoformat()+"T15:00:00":log(a,now,"本月决策晚于收盘，跳过成交");a["pending"]=None;return a
        if not all(quotes.get(c,{}).get("quote_time","")>=now.date().isoformat()+"T15:00:00" for c in [a["rules"]["dividend_code"],a["rules"]["growth_code"]]):return a
        execute(a,quotes,now)
    elif in_session:execute(a,quotes,now)
    return a


def run_once():
    if not _run_lock.acquire(blocking=False):return
    try:
        now=datetime.now(TZ)
        with _lock:
            with database() as db:a=read(db)
        if not a:return
        codes=[a["rules"]["dividend_code"],a["rules"]["growth_code"]]
        # 联网不占用账户控制锁，暂停按钮无需等待供应商超时。
        feed=rates(now)
        q={r["code"]:r for r in fetch_quotes(codes)["quotes"]}
        events={c:actions(c,now) for c in codes}
        calendar=[]
        if a["status"]=="running" and (now.strftime("%Y-%m")>a["last_month"] or (a.get("pending") or {}).get("kind")=="monthly"):
            calendar=fetch_daily(codes[0],30,adjust="").trade_date.tolist()
        now=datetime.now(TZ)
        with _lock:
            with database() as db:
                # 重新读取控制后的账本，不能用联网前的快照覆盖暂停/退出。
                a=read(db)
                apply_actions(a,events,now)
                step(a,q,now,feed,calendar)
                save(db,a)
        _runtime.update(state="运行中" if a["status"]=="running" else a["status"],error=None,updated_at=now.isoformat())
    except Exception as exc:_runtime.update(state="等待有效数据",error=str(exc)[:250],updated_at=datetime.now(TZ).isoformat())
    finally:_run_lock.release()


@router.get("")
def status():
    with database() as db:a=read(db)
    feed=cached("overnight")
    runtime=dict(_runtime)
    if a and runtime["updated_at"] is None:runtime.update(state="账本已载入，后台恢复中")
    return dict(account=a,runtime=runtime,feed={k:v for k,v in (feed or {}).items() if k!="rows"},note="前向模拟从实际启动时刻计；回测不计入账户收益。20%为退出触发线，不保证极端行情亏损上限。月末信号次月首交易日收盘模型，未模拟盘口队列；当前只模拟512890与159915。")


@router.post("/{action}")
def control(action:str):
    if action not in ["start","pause","exit"]:raise HTTPException(404,"未知模拟动作")
    with _lock:
        now=datetime.now(TZ)
        with database() as db:
            a=read(db) or new_account(now,load_config())
            if action=="pause":a["status"]="paused"
            elif action=="exit":a.update(status="running",risk_exit=True,pending=dict(kind="exit",created_at=now.isoformat(),dividend_weight=0.,growth_weight=0.,reason="人工请求模拟退出"))
            else:
                if a.get("risk_triggered") or a["status"]=="risk_paused":raise HTTPException(409,"已触发风险退出，保留账本暂停状态；须先复核风险，不自动重启")
                a["status"]="running"
            log(a,now,{"start":"隔夜SHIBOR模拟已启动，使用独立10万元虚拟资金，不回填过去成交","pause":"模拟已暂停","exit":"已记录模拟退出请求"}[action]);save(db,a)
    _executor.submit(run_once);return status()
