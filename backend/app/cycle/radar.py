"""市场雷达只提供可核对的事实，不生成综合评分或仓位指令。"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Lock
from time import monotonic
import copy

from fastapi import APIRouter

from app.cycle.engine import load_config
from app.cycle.live import LiveDataProvider, TZ, number
from app.cycle.market import fetch_daily, fetch_quotes

router = APIRouter(prefix="/market", tags=["市场雷达"])
_cache = {}
_lock = Lock()


def trend_facts(frame):
    if len(frame) < 21:
        raise ValueError("完整日线不足21根")
    close = float(frame.close.iloc[-1])
    previous_volume = float(frame.volume.iloc[-21:-1].mean())
    return dict(symbol="510300", name="沪深300ETF", date=str(frame.trade_date.iloc[-1]), close=close,
        ma20=float(frame.close.tail(20).mean()), ma60=float(frame.close.tail(60).mean()) if len(frame) >= 60 else None,
        ma200=float(frame.close.tail(200).mean()) if len(frame) >= 200 else None,
        volume=float(frame.volume.iloc[-1]), prior20_volume=previous_volume,
        volume_ratio=float(frame.volume.iloc[-1]) / previous_volume if previous_volume > 0 else None,
        source="腾讯前复权完整日线", scope="单只宽基ETF样本；成交量不代表全市场成交额或资金净流入")


def sector_facts(rows, expected_date=None):
    if expected_date is None:
        dates = [datetime.fromtimestamp(number(r.get("f124")), TZ).date().isoformat() for r in rows if number(r.get("f124"))]
        expected_date = max(dates) if dates else None
    result = []
    missing = 0
    for row in rows:
        stamp = number(row.get("f124"))
        timestamp = datetime.fromtimestamp(stamp, TZ).isoformat() if stamp else None
        change = number(row.get("f3"))
        if timestamp is None or change is None or (expected_date and timestamp[:10] != expected_date):
            missing += 1
            continue
        result.append(dict(code=row["f12"], name=row["f14"], pct=change, quote_time=timestamp))
    result.sort(key=lambda r: (-r["pct"], r["code"]))
    for index, row in enumerate(result, 1):
        row["rank"] = index
    return dict(rows=result, data_date=expected_date, covered=len(result), source_total=len(rows), omitted=missing,
        advancing=sum(r["pct"] > 0 for r in result), declining=sum(r["pct"] < 0 for r in result), flat=sum(r["pct"] == 0 for r in result),
        source="东方财富行业板块", scope="行业板块数量，非上涨/下跌股票家数；排名仅按当日涨跌幅，不代表产业景气或资金净流入")


def fetch_radar(config):
    values, feeds = {}, {}
    try:
        quote = fetch_quotes(["sh000001"])["quotes"][0]
        quote_time = quote["quote_time"]
        feeds["reference_quote"] = dict(status="正常")
    except Exception:
        quote_time = None
        feeds["reference_quote"] = dict(status="不可用", note="无有效参考报价日期，股票池保持未知")
    date = quote_time[:10] if quote_time else None
    provider = LiveDataProvider(config)
    try:
        tasks = {"trend": lambda: trend_facts(fetch_daily("510300", 320)), "sectors": lambda: sector_facts(provider.sectors(), date)}
        if date:
            compact = date.replace("-", "")
            for name, endpoint in (("limit_up", "getTopicZTPool"), ("limit_down", "getTopicDTPool"), ("broken", "getTopicZBPool")):
                tasks[name] = lambda endpoint=endpoint: provider.pool(endpoint, compact)
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {name: executor.submit(fn) for name, fn in tasks.items()}
            for name, future in futures.items():
                try:
                    values[name] = future.result()
                    feeds[name] = dict(status="无有效同日数据" if name == "sectors" and not values[name]["covered"] else "正常", fetched_at=datetime.now(TZ).isoformat())
                except Exception:
                    values[name] = None
                    feeds[name] = dict(status="不可用", note="上游请求失败或数据不完整，相关值留空")
    finally:
        provider.client.close()
    up, down, broken = (values.get(k) for k in ("limit_up", "limit_down", "broken"))
    attempts = len(up) + len(broken) if up is not None and broken is not None else None
    now = datetime.now(TZ)
    intraday = now.weekday() < 5 and ("09:30" <= now.strftime("%H:%M") <= "11:30" or "13:00" <= now.strftime("%H:%M") <= "15:00")
    return dict(fetched_at=now.isoformat(), quote_time=quote_time, data_date=date, refresh_seconds=config["live_refresh_seconds"],
        session="盘中候选数据" if intraday else "非连续交易时段 · 最近报价",
        stale=bool(intraday and quote_time and (now-datetime.fromisoformat(quote_time)).total_seconds() > config["live_stale_seconds"]),
        trend=values.get("trend"), sectors=values.get("sectors"), feeds=feeds,
        sentiment=dict(date=date, limit_up=len(up) if up is not None else None, limit_down=len(down) if down is not None else None,
            break_rate=len(broken) / attempts * 100 if attempts else 0 if attempts == 0 else None,
            source="东方财富涨停/跌停/炸板池", scope="股票池仅有行情日，秒级延迟未知；与情绪周期同一数据源及炸板率公式"),
        note="只展示事实及数据范围；政策和产业证据由用户记录，不自动确认，不输出市场总分或权益仓位。")


@router.get("/radar")
def radar():
    config = load_config()
    with _lock:
        if _cache and monotonic() - _cache.get("time", 0) < config["live_cache_seconds"]:
            return copy.deepcopy(_cache["data"])
        data = fetch_radar(config)
        _cache.update(time=monotonic(), data=data)
        return copy.deepcopy(data)
