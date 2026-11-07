"""旧终端能力迁入：真实数据诊断、基金深研及明确标注假设的组合推演。"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import math
import re
from zoneinfo import ZoneInfo

import httpx
import numpy as np
import pandas as pd

from app.cycle.live import TZ, number
from app.cycle.market import fetch_daily, fetch_quotes
from app.services.data_ingestion import fetch_history
from app.services.news_sentiment import _fetch_headlines


def finite(value):
    return float(value) if value is not None and math.isfinite(float(value)) else None


def metrics(prices, risk_free=0.02):
    p = pd.Series(prices, dtype=float).dropna()
    if len(p) < 2 or (p <= 0).any():
        raise ValueError("至少需要两个有效正价格")
    r = p.pct_change().dropna()
    drawdown = p / p.cummax() - 1
    annual = (p.iloc[-1] / p.iloc[0]) ** (252 / len(r)) - 1
    vol = r.std() * np.sqrt(252)
    downside = np.sqrt(np.mean(np.minimum(r - risk_free / 252, 0) ** 2)) * np.sqrt(252)
    var = max(0, -float(r.quantile(.05)))
    tail = r[r <= r.quantile(.05)]
    gains, losses = r[r > 0], r[r < 0]
    mdd = float(drawdown.min())
    return {"total_return": finite((p.iloc[-1] / p.iloc[0] - 1) * 100), "annual_return": finite(annual * 100),
        "volatility": finite(vol * 100), "sharpe": finite((r.mean() * 252 - risk_free) / vol) if vol > 0 else None,
        "sortino": finite((r.mean() * 252 - risk_free) / downside) if downside > 0 else None,
        "calmar": finite(annual / abs(mdd)) if mdd else None, "max_drawdown": mdd * 100,
        "var95": var * 100, "cvar95": max(0, -float(tail.mean())) * 100,
        "win_rate": float((r > 0).mean() * 100), "profit_loss_ratio": finite(gains.mean() / abs(losses.mean())) if len(gains) and len(losses) else None,
        "samples": len(p)}


def technical_frame(frame):
    df = frame.copy().reset_index(drop=True)
    close = df.close.astype(float)
    delta = close.diff()
    gain, loss = delta.clip(lower=0).rolling(14).mean(), (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi"] = (100 - 100 / (1 + rs)).where(loss != 0, 100).where((gain + loss) != 0, 50)
    for n in [20, 50, 200]:
        df[f"ma{n}"] = close.rolling(n).mean()
    df["ema12"], df["ema26"] = close.ewm(span=12, adjust=False).mean(), close.ewm(span=26, adjust=False).mean()
    df["macd"] = df.ema12 - df.ema26
    df["signal"] = df.macd.ewm(span=9, adjust=False).mean()
    df["histogram"] = df.macd - df.signal
    df["upper"], df["lower"] = df.ma20 + close.rolling(20).std() * 2, df.ma20 - close.rolling(20).std() * 2
    df["drawdown"] = (close / close.cummax() - 1) * 100
    df["rolling_volatility"] = close.pct_change().rolling(20).std() * np.sqrt(252) * 100
    return df


def records(frame):
    return [{k: (None if pd.isna(v) else v.item() if hasattr(v, "item") else v) for k, v in row.items()} for row in frame.to_dict("records")]


def diagnose(symbol, count=252, capital=100000, risk_budget_pct=1, max_position_pct=10):
    symbol = symbol.strip().upper()
    mainland = bool(re.fullmatch(r"\d{6}(?:\.(?:SS|SH|SZ|BJ))?", symbol))
    if not mainland and not re.fullmatch(r"[A-Z][A-Z0-9-]{0,14}", symbol):
        raise ValueError("请输入六位A股代码或美股代码；其他境外市场暂未确认币种，不混算美元")
    if mainland:
        history = fetch_daily(symbol, count)
        quote = fetch_quotes([symbol])
        source = "腾讯前复权日线 / 公开报价"
    else:
        history = fetch_history(symbol).tail(count)
        local = datetime.now(ZoneInfo("America/New_York"))
        if local.hour < 16:
            history = history[history.trade_date.astype(str) < local.date().isoformat()]
        quote = {"quotes": [], "notes": "跨市场研究：美元计价，仅有已完成日线，不冒充实时报价。"}
        source = "Yahoo Finance 前复权日线"
    if len(history) < 30:
        raise ValueError("有效日线不足30根，未生成诊断")
    history = history.copy()
    history["trade_date"] = history.trade_date.astype(str)
    frame = technical_frame(history)
    m = metrics(history.close)
    latest = records(frame.tail(1))[0]
    budget = capital * risk_budget_pct / 100
    stop_pct = max(m["var95"] / 100 * 2, .03)
    cap = min(capital * max_position_pct / 100, budget / stop_pct)
    warnings = ["技术信号与历史风险统计不是未来预测；VaR无法覆盖全部尾部风险。"]
    if latest["rsi"] is not None and latest["rsi"] > 70:
        warnings.append("RSI位于高位区间，关注追涨风险。")
    if latest["ma200"] is not None and latest["close"] < latest["ma200"]:
        warnings.append("价格低于200日均线，长期趋势仍弱。")
    if m["max_drawdown"] <= -20:
        warnings.append("样本内最大回撤超过20%，需检查组合风险预算。")
    try:
        news = {"items": _fetch_headlines(symbol), "status": "已获取真实资讯", "source": "东方财富资讯" if mainland else "Yahoo Finance资讯"}
    except Exception:
        news = {"items": [], "status": "资讯源暂不可用，未构造新闻或情绪结论"}
    return dict(kind="stock", code=symbol, currency="CNY" if mainland else "USD", name=quote["quotes"][0]["name"] if quote["quotes"] else symbol,
        source=source, quote=quote, as_of=history.trade_date.max(), fetched_at=datetime.now(TZ).isoformat(), metrics=m,
        latest=latest, chart=records(frame), news=news, warnings=warnings,
        sizing=dict(capital=capital, risk_budget=budget, stop_assumption_pct=stop_pct * 100, position_cap=cap, max_position_pct=max_position_pct,
            note="基于历史VaR构造的止损幅度假设和仓位上限；跳空、跌停可能突破风险预算，不自动下单。"),
        summary="均线、动量与风险三部分并列复核；证据不足时保持观察，不生成无依据的胜率。")


def nav_history(code, days=640):
    rows = []
    with httpx.Client(trust_env=False, timeout=12, headers={"Referer": "https://fundf10.eastmoney.com/"}) as client:
        def page_data(page):
            response = client.get("https://api.fund.eastmoney.com/f10/lsjz", params={"fundCode": code, "pageIndex": page, "pageSize": 20})
            response.raise_for_status()
            payload = response.json()
            chunk = (payload.get("Data") or {}).get("LSJZList") or []
            return chunk, int(payload.get("TotalCount") or len(chunk))
        first, total = page_data(1)
        rows.extend(first)
        with ThreadPoolExecutor(max_workers=2) as pool:
            for chunk, current_total in pool.map(page_data, range(2, math.ceil(min(days, total) / 20) + 1)):
                if current_total != total or not chunk:
                    raise ValueError("基金净值分页不完整，请重试")
                rows.extend(chunk)
    if not rows:
        raise ValueError("基金净值源没有返回有效记录")
    frame = pd.DataFrame([dict(date=r["FSRQ"], nav=number(r.get("DWJZ")), acc_nav=number(r.get("LJJZ"))) for r in rows])
    if frame.date.duplicated().any():
        raise ValueError("基金净值分页重复，未生成历史统计")
    return frame.drop_duplicates("date").sort_values("date").dropna(subset=["nav"]).tail(days)


def fund_deep(code, count=252, warning_high=1.5, danger_high=3, warning_low=-1.5, danger_low=-3):
    from app.services.fund_data import detect_fund_type
    from app.services.fund_analysis import get_premium_snapshot
    if not re.fullmatch(r"\d{6}", code):
        raise ValueError("基金代码必须为六位数字")
    if not danger_low < warning_low < 0 < warning_high < danger_high:
        raise ValueError("折溢价阈值顺序无效")
    kind = detect_fund_type(code)
    nav = nav_history(code, count)
    warnings, premium = [], None
    if kind != "OTC":
        price = fetch_daily(code, count, adjust="").rename(columns={"trade_date": "date"})
        # 不将净值发布日期倒移，不前填；相同估值日期的事后研究，不能当作当时可得IOPV。
        joined = price.merge(nav, on="date", how="left")
        valid = joined.dropna(subset=["nav"])
        premium_series = [dict(date=r["date"], premium=(r["close"] / r["nav"] - 1) * 100) for r in valid.to_dict("records") if r["nav"] > 0]
        series = price.close
        chart = records(joined)
        try:
            snap = get_premium_snapshot(code, kind)
            if snap:
                premium = snap.__dict__.copy()
                rate = snap.premium_rate
                premium["alert_level"] = "危险" if rate >= danger_high or rate <= danger_low else "预警" if rate >= warning_high or rate <= warning_low else "正常"
        except Exception:
            warnings.append("当前价格/IOPV接口不可用，未以历史净值冒充实时折溢价。")
        source = "腾讯未复权场内价格 + 东方财富官方单位净值/IOPV"
    else:
        chart = records(nav.assign(close=nav.nav))
        series = nav.acc_nav if nav.acc_nav.notna().all() else nav.nav
        premium_series, source = [], "东方财富已公布单位/累计净值；不使用盘中估值冒充净值"
    m = metrics(series)
    chart = records(technical_frame(pd.DataFrame(chart)))
    values = pd.Series([r["premium"] for r in premium_series], dtype=float)
    stats = {"samples": len(values), "mean": finite(values.mean()), "median": finite(values.median()), "p5": finite(values.quantile(.05)), "p95": finite(values.quantile(.95)),
        "current_percentile": finite((values <= premium["premium_rate"]).mean() * 100) if premium and len(values) else None}
    returns = {str(n): finite((float(series.iloc[-1]) / float(series.iloc[-min(n + 1, len(series))]) - 1) * 100) if len(series) > n else None for n in (21, 63, 126, 252)}
    warnings.extend(["历史收盘价/净值按估值所属日期严格匹配，仅供事后研究；净值披露时间、时差与IOPV不同，不用于可成交套利或历史信号。", "场内未复权价格收益不包含分红再投资；场外累计净值比值亦不等同严格分红再投资收益。"])
    return dict(kind="fund", code=code, name=premium["name"] if premium else code, fund_type=kind, source=source,
        as_of=chart[-1]["date"], fetched_at=datetime.now(TZ).isoformat(), metrics=m, chart=chart,
        premium=premium, premium_history=premium_series, premium_stats=stats, period_returns=returns, warnings=warnings)


def fund_holdings(code):
    import akshare as ak
    frame = ak.fund_portfolio_hold_em(symbol=code, date=str(datetime.now(TZ).year))
    if frame.empty:
        raise ValueError("未获取该基金已披露持仓")
    if "季度" in frame:
        frame = frame[frame["季度"] == frame["季度"].max()]
    return {"source": "东方财富基金定期报告，经AkShare读取", "note": "定期披露持仓，非当前实时持仓；报告期见每行季度。", "rows": records(frame.head(10))}


def fund_estimate(code):
    with httpx.Client(trust_env=False, timeout=12) as client:
        response = client.get(f"https://fundgz.1234567.com.cn/js/{code}.js")
        response.raise_for_status()
    match = re.fullmatch(r"jsonpgz\((.*)\);?", response.text.strip())
    if not match or not match[1]:
        raise ValueError("该基金没有可用盘中估值；不以最新净值替代估值")
    import json
    row = json.loads(match[1])
    return {"source": "天天基金盘中估值（非官方净值）", "name": row.get("name"), "estimate_time": row.get("gztime"), "nav_date": row.get("jzrq"), "published_nav": number(row.get("dwjz")), "estimated_nav": number(row.get("gsz")), "estimated_change_pct": number(row.get("gszzl")), "note": "供应商估算，可能偏离实际净值；估值与官方净值日期分别展示，不作为成交或套利证据。"}


def rankings(order="amount"):
    fid, direction = ("f3", 0) if order == "losers" else ("f3", 1) if order == "gainers" else ("f6", 1)
    with httpx.Client(trust_env=False, timeout=12) as client:
        r = client.get("https://push2.eastmoney.com/api/qt/clist/get", params={"fs": "b:MK0021,b:MK0022,b:MK0023,b:MK0024", "fid": fid, "po": direction, "pn": 1, "pz": 20, "fltt": 2, "fields": "f12,f14,f2,f3,f6,f124"})
        r.raise_for_status()
        data = r.json().get("data") or {}
    rows = data.get("diff") or []
    if isinstance(rows, dict):
        rows = list(rows.values())
    if not rows:
        raise ValueError("ETF排行源未返回数据")
    return {"source": "东方财富ETF排行", "coverage": data.get("total"), "rows": [dict(code=r["f12"], name=r["f14"], price=number(r.get("f2")), pct=number(r.get("f3")), amount=number(r.get("f6")), quote_time=datetime.fromtimestamp(r["f124"], TZ).isoformat() if number(r.get("f124")) else None) for r in rows]}


def monte_carlo(capital, monthly, years, annual_return, volatility, target, simulations=2000, seed=42):
    rng = np.random.default_rng(seed)
    values = np.full(simulations, float(capital))
    path = [dict(month=0, p5=capital, median=capital, p95=capital, contributed=capital)]
    for month in range(1, years * 12 + 1):
        values *= np.exp((annual_return - volatility ** 2 / 2) / 12 + volatility / np.sqrt(12) * rng.normal(size=simulations))
        values += monthly
        q = np.quantile(values, [.05, .5, .95])
        path.append(dict(month=month, p5=float(q[0]), median=float(q[1]), p95=float(q[2]), contributed=capital + monthly * month))
    return dict(kind="simulation", code="组合推演", name="假设情景", source="几何布朗运动假设模型，不是真实行情或收益预测", path=path,
        target_probability=float((values >= target).mean() * 100), mean_final=float(values.mean()), loss_probability=float((values < capital + monthly * years * 12).mean() * 100), seed=seed,
        assumptions=dict(capital=capital, monthly=monthly, years=years, annual_return=annual_return, volatility=volatility, target=target, simulations=simulations),
        warnings=["概率只表示输入假设下的模拟占比；未覆盖跳跃、肥尾、制度变化、税费和流动性，不是实际达标概率。", "按月模拟、月末追加资金；固定随机种子便于复核。"], fetched_at=datetime.now(TZ).isoformat())
