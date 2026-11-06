"""全项目共享的真实报价和历史日线；只有读取行情的接口。"""
from datetime import datetime
from threading import Lock
from time import monotonic
import re

from fastapi import APIRouter, HTTPException, Query
import httpx
import pandas as pd

from app.cycle.live import TZ, number
from app.cycle.engine import load_config

router = APIRouter(prefix="/market", tags=["真实行情"])
_cache = {}
_lock = Lock()


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
    codes = sorted(set(normalize_symbol(s) for s in symbols))
    if not codes or len(codes) > 100:
        raise ValueError("每次查询1至100个代码")
    config = load_config()
    key = "quote:"+",".join(codes)
    with _lock:
        cached = _cache.get(key)
        if cached and monotonic()-cached[0] < config["live_cache_seconds"]:
            return cached[1]
    with httpx.Client(trust_env=False, timeout=config["live_timeout_seconds"]) as client:
        response = client.get("https://qt.gtimg.cn/q="+",".join(codes))
        response.raise_for_status()
    rows = []
    for symbol, raw in re.findall(r'v_(\w+)="([^"]*)"', response.content.decode("gb18030", errors="replace")):
        f = raw.split("~")
        if len(f) < 47 or number(f[3]) is None or not f[30]:
            continue
        stamp = datetime.strptime(f[30], "%Y%m%d%H%M%S").replace(tzinfo=TZ)
        rows.append(dict(symbol=symbol, code=f[2], name=f[1], price=number(f[3]), previous_close=number(f[4]), open=number(f[5]), high=number(f[33]), low=number(f[34]), pct=number(f[32]), pe=number(f[39]), pe_basis="供应商动态市盈率", pb=number(f[46]), dividend_yield=None, volume_lots=number(f[6]), amount_yuan=number(f[37])*10000 if number(f[37]) is not None else None, quote_time=stamp.isoformat(), currency="CNY"))
    payload = dict(provider="腾讯公开行情", fetched_at=datetime.now(TZ).isoformat(), refresh_seconds=config["live_refresh_seconds"], quotes=rows, missing=[code for code in codes if code not in {r["symbol"] for r in rows}], notes="股息率未由该接口验证，保留为空；场内基金不适用公司PE/PB。")
    with _lock:
        if len(_cache) > 300:
            _cache.clear()
        _cache[key] = (monotonic(), payload)
    return payload


def fetch_daily(symbol, count=640, adjust="qfq"):
    code = normalize_symbol(symbol)
    count = max(30, min(640, int(count)))
    config = load_config()
    key = f"history:{code}:{count}:{adjust}"
    with _lock:
        cached = _cache.get(key)
        if cached and monotonic()-cached[0] < config["live_cache_seconds"]:
            return cached[1].copy()
    with httpx.Client(trust_env=False, timeout=config["live_timeout_seconds"]) as client:
        response = client.get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get", params={"param": f"{code},day,,,{count},{adjust}"})
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
    with _lock:
        _cache[key] = (monotonic(), frame.copy())
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
        from app.services.backtest_engine import run_comparison
        frame = fetch_daily(symbol, 640)
        close = pd.Series(frame.close.values, index=pd.DatetimeIndex(frame.trade_date))
        results = run_comparison(close)
        for result in results:
            result["equity_curve"] = {str(d.date()):float(value) for d,value in result["equity_curve"].items()}
        return dict(provider="腾讯真实前复权日线", symbol=normalize_symbol(symbol), as_of=frame.trade_date.max(), results=results, note="历史策略实验，非已实现账户业绩；含模型费用，未完整还原A股涨跌停与T+1成交，不得用作真实交易收益。")
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(503, str(exc)[:160]) from exc
