"""全项目共享的真实报价和历史日线；只有读取行情的接口。

腾讯报价只有这里一处抓取+解析实现：`fetch_quotes` 供全项目股票消费方使用，`cycle/live.py`
的指数行情也委托 `fetch_quote_rows`/`parse_quotes`，不再各自维护正则和字段下标。
"""
from datetime import datetime
from threading import Lock, BoundedSemaphore
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from time import monotonic
import re

from fastapi import APIRouter, HTTPException, Query
import httpx
import pandas as pd

from app.cycle.live import TZ, number
from app.cycle.engine import load_config

router = APIRouter(prefix="/market", tags=["真实行情"])
_cache = {}
_daily_cache = {}
_lock = Lock()
_quote_flights={}
_daily_flights={}
_daily_bytes=0
_quote_slots=BoundedSemaphore(6)

QUOTE_URL = "https://qt.gtimg.cn/q="
# 严格档：腾讯对个股和指数都返回 47 个以上字段；要求 PE(f39)/PB(f46) 一定存在，
# 不再使用 live.py 旧的 >=38 宽松档（该档下 f39/f46 可能越界）。
QUOTE_MIN_FIELDS = 47


def parse_quotes(text):
    """把腾讯 qt.gtimg.cn 的 `v_<代码>="..."` 响应解析为报价字典（全项目唯一解析实现）。

    字段口径：`amount_yuan` 统一为元（供应商 f37 单位万元，乘 10000）；`quote_time` 为
    供应商时间戳加 Asia/Shanghai 时区。`len(fields) >= 47` 取更严格的一档，保证 PE/PB
    下标 f39/f46 存在（场内基金不适用公司 PE/PB，按代码前缀置空，字段仍保留）。
    """
    rows = []
    for symbol, raw in re.findall(r'v_(\w+)="([^"]*)"', text):
        f = raw.split("~")
        if len(f) < QUOTE_MIN_FIELDS or number(f[3]) is None or not f[30]:
            continue
        try:
            stamp = datetime.strptime(f[30], "%Y%m%d%H%M%S").replace(tzinfo=TZ)
        except ValueError:
            continue
        rows.append(dict(symbol=symbol, code=f[2], name=f[1], price=number(f[3]), previous_close=number(f[4]), open=number(f[5]), high=number(f[33]), low=number(f[34]), pct=number(f[32]), pe=None if symbol.startswith(("sh5","sz15","sz16")) else number(f[39]), pe_basis="供应商动态市盈率", pb=None if symbol.startswith(("sh5","sz15","sz16")) else number(f[46]), dividend_yield=None, volume_lots=number(f[6]), amount_yuan=number(f[37])*10000 if number(f[37]) is not None else None, quote_time=stamp.isoformat(), currency="CNY"))
    return rows


def fetch_quote_rows(codes, client):
    """用调用方持有的 HTTP client 抓取并解析腾讯报价（不缓存，client 生命周期由调用方管理）。

    `codes` 为已归一化的腾讯代码（`normalize_symbol` 的输出或 `sh`/`sz`/`bj` + 六位）。
    `cycle/live.py` 用注入 transport 的 client 调它，从而只保留一份抓取+解析实现。
    """
    response = client.get(QUOTE_URL + ",".join(codes))
    response.raise_for_status()
    return parse_quotes(response.content.decode("gb18030", errors="replace"))


def normalize_symbol(symbol):
    symbol = symbol.strip().upper()
    if re.fullmatch(r"(?:SH|SZ|BJ)\d{6}", symbol):
        return symbol.lower()
    match = re.fullmatch(r"(\d{6})(?:\.(SS|SH|SZ|BJ))?", symbol)
    if not match:
        raise ValueError("仅支持六位A股或场内基金代码，例如600519、600519.SS、510300")
    code, suffix = match.groups()
    exchange = {"SS":"sh", "SH":"sh", "SZ":"sz", "BJ":"bj"}.get(suffix)
    return (exchange or ("sh" if code.startswith(("5", "6", "9")) and not code.startswith("92") else "bj" if code.startswith(("4", "8", "92")) else "sz"))+code


def fetch_quotes(symbols):
    codes=sorted(set(normalize_symbol(s) for s in symbols))
    if not codes or len(codes)>100:raise ValueError("每次查询1至100个代码")
    cfg=load_config();pending={};owned=[]
    with _lock:
        for code in codes:
            old=_cache.get("quote:"+code)
            if old and monotonic()-old[0]<cfg["live_cache_seconds"]:
                f=Future();f.set_result(old[1]);pending[code]=f
            else:
                f=_quote_flights.get(code)
                if f is None:f=Future();_quote_flights[code]=f;owned.append(code)
                pending[code]=f
    if owned:
        try:
            with _quote_slots:
                with httpx.Client(trust_env=False,timeout=cfg["live_timeout_seconds"]) as client:rows=fetch_quote_rows(owned,client)
            stamp=datetime.now(TZ).isoformat();lookup={r["symbol"]:r for r in rows};now=monotonic()
            with _lock:
                for code in owned:
                    cell=(stamp,lookup.get(code));_cache["quote:"+code]=(now,cell)
                    _quote_flights.pop(code,None);pending[code].set_result(cell)
                while len(_cache)>16000:_cache.pop(next(iter(_cache)))
        except Exception as exc:
            with _lock:
                for code in owned:_quote_flights.pop(code,None);pending[code].set_exception(exc)
            raise
    cells=[pending[c].result() for c in codes]
    rows=[dict(cell[1]) for cell in cells if cell[1] is not None]
    return dict(provider="腾讯公开行情",fetched_at=min(c[0] for c in cells),refresh_seconds=cfg["live_refresh_seconds"],quotes=rows,missing=[code for code,cell in zip(codes,cells) if cell[1] is None],notes="股息率未由该接口验证，保留为空；场内基金不适用公司PE/PB。")


def quote_batches(symbols,workers=4):
    """仅改变批次并行度；保留100个/批和缺失标记，给交互/持仓查询预留请求容量。"""
    codes=sorted(set(symbols));quotes={};failures=[]
    with ThreadPoolExecutor(max_workers=min(4,max(1,workers))) as pool:
        jobs={pool.submit(fetch_quotes,codes[i:i+100]):codes[i:i+100] for i in range(0,len(codes),100)}
        for job in as_completed(jobs):
            try:quotes.update({q["code"]:q for q in job.result()["quotes"]})
            except Exception as exc:failures.append(dict(codes=jobs[job],error=str(exc)[:150]))
    return quotes,failures


def fetch_daily(symbol,count=640,adjust="qfq"):
    global _daily_bytes
    code=normalize_symbol(symbol);count=max(30,min(640,int(count)));cfg=load_config();now=datetime.now(TZ)
    key=f"history:{code}:{count}:{adjust}:{now.date()}:{now.hour>=15}"
    with _lock:
        old=_daily_cache.get(key)
        if old and monotonic()-old[0]<cfg["live_daily_cache_seconds"]:
            _daily_cache.pop(key);_daily_cache[key]=old;return old[1].copy()
        future=_daily_flights.get(key);owner=future is None
        if owner:future=Future();_daily_flights[key]=future
    if not owner:return future.result().copy()
    try:
        frame=_fetch_daily_uncached(symbol,count,adjust)
        size=int(frame.memory_usage(index=True,deep=True).sum())
        with _lock:
            if not _daily_cache:_daily_bytes=0
            previous=_daily_cache.pop(key,None)
            if previous:_daily_bytes-=previous[2]
            _daily_cache[key]=(monotonic(),frame,size);_daily_bytes+=size
            while _daily_bytes>128*1024*1024 and len(_daily_cache)>1:
                oldest=_daily_cache.pop(next(iter(_daily_cache)));_daily_bytes-=oldest[2]
            _daily_flights.pop(key,None);future.set_result(frame)
        return frame.copy()
    except Exception as exc:
        with _lock:_daily_flights.pop(key,None);future.set_exception(exc)
        raise


def _fetch_daily_uncached(symbol, count=640, adjust="qfq"):
    code = normalize_symbol(symbol)
    count = max(30, min(640, int(count)))
    config = load_config()
    now = datetime.now(TZ)
    # 收盘前后分别缓存，避免15点后沿用盘中剔除当日K线的结果。
    with httpx.Client(trust_env=False, timeout=config["live_timeout_seconds"]) as client:
        response = client.get("https://web.ifzq.gtimg.cn/appstock/app/newfqkline/get", params={"param": f"{code},day,,,{count},{adjust}"})
        response.raise_for_status()
        data = response.json().get("data", {}).get(code, {})
    rows = data.get(adjust+"day", data.get("day", []))
    if not rows:
        raise ValueError("供应商没有返回该代码的真实日线")
    frame = pd.DataFrame([dict(trade_date=r[0], open=float(r[1]), close=float(r[2]), high=float(r[3]), low=float(r[4]), volume=float(r[5])*100) for r in rows])
    # 盘中未完成的日K不参与历史回测、财务趋势和选股统计。
    now = datetime.now(TZ)
    if now.strftime("%H:%M") < "15:00":
        frame = frame[frame.trade_date < now.date().isoformat()]
    return frame


@router.get("/quotes")
def quotes(symbols: str = Query("600519,000858,601318,600036,000333,300750,002594,600900,601668,510300", max_length=2000)):
    try:
        return fetch_quotes(symbols.split(","))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, "真实行情源请求失败："+str(exc)[:120]) from exc


@router.get("/history/{symbol}")
def history(symbol: str, count: int = Query(320, ge=30, le=640)):
    try:
        data = fetch_daily(symbol, count)
        return dict(provider="腾讯真实前复权日线", symbol=normalize_symbol(symbol), fetched_at=datetime.now(TZ).isoformat(), data_through=data.trade_date.max() if not data.empty else None, adjustment="qfq", bars=data.rename(columns={"trade_date":"date"}).to_dict("records"))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, "日线请求失败："+str(exc)[:120]) from exc


@router.get("/allocation")
def allocation():
    try:
        equity, bonds = fetch_daily("510300", 640), fetch_daily("511010", 320)
        if len(equity) < 200 or len(bonds) < 64:
            raise ValueError("历史不足200/64个交易日，无法计算趋势")
        ma = float(equity.close.tail(200).mean())
        return dict(provider="腾讯真实前复权日线", as_of=min(equity.trade_date.max(), bonds.trade_date.max()), equity_symbol="510300", bond_symbol="511010", equity_vs_ma200_pct=(float(equity.close.iloc[-1])/ma-1)*100, bond_return_63d_pct=(float(bonds.close.iloc[-1])/float(bonds.close.iloc[-64])-1)*100, note="只展示沪深300ETF与国债ETF价格趋势，不能据此推断GDP/CPI或债券收益率；仓位仍由个人风险预算决定。")
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(503, str(exc)[:160]) from exc


@router.get("/strategy-lab")
def strategy_lab(symbol: str = "510300"):
    try:
        from app.cycle.engine import load_config
        from app.cycle.relative_backtest import run_relative_trend
        from app.services.backtest_engine import run_comparison
        frame = fetch_daily(symbol, 640)
        close = pd.Series(frame.close.values, index=pd.DatetimeIndex(frame.trade_date))
        results = run_comparison(close)
        warnings = []
        # 只有纯价量规则可以做诚实回测；其余 A股策略依赖历史财务/事件快照，仅保留前向模拟。
        try:
            benchmark = fetch_daily("510300", 640)
            results.append(run_relative_trend(frame, benchmark, float(load_config()["research_relative_min_pp"])))
        except (ValueError, httpx.HTTPError, KeyError) as exc:
            warnings.append("A股相对强势规则回测不可用：" + str(exc)[:120])
        for result in results:
            result["equity_curve"] = {str(d.date()):float(value) for d,value in result["equity_curve"].items()}
        return dict(provider="腾讯真实前复权日线", symbol=normalize_symbol(symbol), as_of=frame.trade_date.max(), results=results, warnings=warnings,
                    note="四类通用技术模板 + A股相对强势规则（仅价量规则）；含模型费用，未完整还原共用风控、T+1与涨跌停成交，不得用作真实交易收益。其余A股策略依赖历史财务/事件数据，只做前向模拟。")
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(503, str(exc)[:160]) from exc
