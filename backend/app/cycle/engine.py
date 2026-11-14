"""按可用时间计算收盘信号；事件研究与现金约束交易模拟分开。"""
import json
import copy
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

CONFIG_PATH = Path(__file__).with_name("config.yaml")


@lru_cache(maxsize=4)
def _validated_config(path,mtime,size):
    # JSON 是 YAML 1.2 子集，避免为现有项目增加解析依赖。
    config = json.loads(Path(path).read_text())
    if not isinstance(config["event_poll_seconds"], int) or not 10 <= config["event_poll_seconds"] <= 3600:
        raise ValueError("事件采集间隔需为10至3600秒")
    if not isinstance(config["research_scan_workers"],int) or not 1 <= config["research_scan_workers"] <= 16:
        raise ValueError("全A股扫描并发需为1至16")
    if not isinstance(config["all_stock_history_bars"],int) or not 30 <= config["all_stock_history_bars"] <= 640:
        raise ValueError("全A股历史窗口需为30至640根日线")
    if not 60<=config["etf_refresh_seconds"]<=86400 or not 0<config["shibor_low_percentile"]<1 or not 1<=config["shibor_smoothing_quotes"]<config["shibor_history_quotes"]:
        raise ValueError("ETF刷新或SHIBOR规则配置不合法")
    if any(config[k]<0 for k in ("shibor_cost_bps","shibor_slippage_bps","shibor_min_commission")) or not 0<=config["shibor_initial_dividend_pct"]<=100:
        raise ValueError("SHIBOR模拟成本或初始配置不合法")
    for key in ('read_cache_document_mb','read_cache_model_mb','read_cache_body_mb','market_daily_cache_mb'):
        if not isinstance(config.get(key),int) or not 1<=config[key]<=4096:raise ValueError("缓存预算需为1至4096MiB")
    if not all(isinstance(config.get(k),int) for k in ('market_quote_slots','market_daily_slots','market_background_slots')) or not all(2<=config[k]<=16 for k in ('market_quote_slots','market_daily_slots')) or not 1<=config['market_background_slots']<min(config['market_quote_slots'],config['market_daily_slots']):
        raise ValueError("行情并发需保留至少一个交互槽位，且不超过16")
    positive = ["market_new_low_lookback_days", "intraday_stop_fall_bars", "intraday_bar_minutes", "sector_start_limit_up_count", "mock_days", "lot_size", "initial_capital"]
    if any(not isinstance(config[k], int) or config[k] <= 0 for k in positive):
        raise ValueError("窗口、样本数、手数与本金必须为正整数")
    if not 0 < config["position_pct"] <= 100 or not 0 <= config["break_rate_risk"] <= 1:
        raise ValueError("仓位或炸板率配置超出范围")
    if any(config[k] < 0 for k in ("buy_cost_bps", "sell_cost_bps", "slippage_bps")):
        raise ValueError("交易成本不能为负")
    if not config["backtest_forward_days"] or any(not isinstance(n, int) or n < 1 for n in config["backtest_forward_days"]):
        raise ValueError("持有期限必须为正整数")
    return config


def load_config():
    stat=CONFIG_PATH.stat()
    return copy.deepcopy(_validated_config(str(CONFIG_PATH),stat.st_mtime_ns,stat.st_size))


def snapshots(frame, as_of, config):
    cutoff = pd.Timestamp(as_of)
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("Asia/Shanghai")
    data = frame[pd.to_datetime(frame.available_at, utc=True) <= cutoff].sort_values(["date", "symbol"])
    history, previous, previous_picks = [], None, []
    for date, group in data.groupby("date", sort=True):
        up = int((group.close >= group.upper_limit).sum())
        down = int((group.close <= group.lower_limit).sum())
        attempts = int(((group.close >= group.upper_limit) | (group.breaks > 0)).sum())
        break_rate = float(((group.close < group.upper_limit) & (group.breaks > 0)).sum()/attempts) if attempts else 0
        yesterday = group[group.symbol.isin(previous_picks)]
        yesterday_pct = float(yesterday.pct.mean()) if not yesterday.empty else None
        leaders = group.sort_values(["boards", "first_limit_time", "seal_ratio", "breaks", "symbol"], ascending=[False, True, False, True, True])
        sectors = []
        for sector, members in group.groupby("sector"):
            pct = float(members.pct.mean())
            count = int((members.close >= members.upper_limit).sum())
            time = members.loc[members.close >= members.upper_limit, "first_limit_time"].min() if count else None
            checks = {"板块涨幅达标": pct >= config["sector_start_pct"], "涨停家数达标": count >= config["sector_start_limit_up_count"], "启动时间达标": bool(time and time <= config["sector_start_before_time"])}
            sectors.append(dict(name=sector, pct=round(pct, 2), limit_up=count, first_time=time, checks=checks, started=all(checks.values())))
        height = int(group.boards.max())
        close = float(group.iloc[0].market_close)
        lows = [r["market_low"] for r in history[-config["market_new_low_lookback_days"]:]]
        new_low = float(group.iloc[0].market_low) < min(lows) if len(lows) >= config["market_new_low_lookback_days"] else None
        risk = down >= config["risk_limit_down_count"] or bool(previous and down-previous["limit_down"] >= config["risk_limit_down_increase"])
        broken_height = bool(previous and previous["height"] >= config["acceleration_height"] and height < previous["height"])
        if risk or (broken_height and yesterday_pct is not None and yesterday_pct < 0):
            state = "退潮"
        elif up <= config["ice_limit_up_count"] and float(group.iloc[0].market_pct) < 0:
            state = "冰点"
        elif previous and previous["state"] == "分歧" and down <= previous["limit_down"] and float(group.pct.mean())-previous["stock_mean"] >= config["refill_sector_pct_recover"]:
            state = "回补"
        elif break_rate >= config["break_rate_risk"]:
            state = "分歧"
        elif any(s["started"] for s in sectors):
            state = "启动"
        elif height >= config["acceleration_height"] and previous and height > previous["height"]:
            state = "加速"
        elif previous and up > previous["limit_up"] and float(group.iloc[0].market_pct) > 0:
            state = "修复"
        else:
            state = "待确认"
        pattern = {"冰点": "冰点龙头", "启动": "启动龙头", "回补": "分歧回补", "分歧": "冲高回落风险", "退潮": "退潮回避"}.get(state, "持续观察")
        checks = {"板块启动": any(s["started"] for s in sectors), "跌停未明显增加": not risk, "昨日涨停表现为正": yesterday_pct is not None and yesterday_pct > 0, "最高板延续": bool(previous and height >= previous["height"])}
        record = dict(date=date, available_at=f"{date}T15:00:00+08:00", state=state, market_close=close, market_low=float(group.iloc[0].market_low), market_pct=float(group.iloc[0].market_pct), market_amount=float(group.iloc[0].market_amount), new_low=new_low,
            limit_up=up, limit_down=down, height=height, break_rate=round(break_rate, 4), seal_rate=round(up/attempts, 4) if attempts else 0, yesterday_pct=yesterday_pct, stock_mean=float(group.pct.mean()), risk="高" if risk else "关注" if break_rate >= config["break_rate_risk"] else "常规",
            sectors=sectors, leaders=leaders[["symbol", "name", "sector", "boards", "pct", "first_limit_time", "seal_ratio", "breaks"]].head(9).to_dict("records"),
            card=dict(pattern=pattern, state=state, checks=checks, action="回避" if state == "退潮" else "等回补" if state == "分歧" else "观察", invalidation="指数再次走弱、候选跌破计划失效价，或跌停扩散；重新评估原信号。", risk="收盘确认；盘中不能提前使用。连板存在隔夜和流动性风险。"), rule_version=config["rule_version"])
        history.append(record)
        previous, previous_picks = record, group.loc[group.close >= group.upper_limit, "symbol"].tolist()
    return history


def event_study(frame, history, config, pattern, horizon):
    rows = []
    for signal in history:
        if signal["card"]["pattern"] != pattern or not signal["leaders"]:
            continue
        symbol = signal["leaders"][0]["symbol"]
        future = frame[(frame.symbol == symbol) & (frame.date > signal["date"])].sort_values("date")
        current = frame[(frame.symbol == symbol) & (frame.date == signal["date"])].iloc[0]
        returns = {str(n): round((float(future.iloc[n-1].close)/float(current.close)-1)*100, 3) if len(future) >= n else None for n in config["backtest_forward_days"]}
        rows.append(dict(date=signal["date"], symbol=symbol, sector=signal["leaders"][0]["sector"], state=signal["state"], returns=returns))
    values = [r["returns"].get(str(horizon)) for r in rows if r["returns"].get(str(horizon)) is not None]
    # 单仓顺序模拟，禁止重叠资金重复使用。
    cash, position, trades, curve = float(config["initial_capital"]), None, [], []
    by_date = {r["date"]: r for r in rows}
    dates = sorted(frame.date.unique())
    pending = None
    for i, date in enumerate(dates):
        today = frame[frame.date == date]
        if position:
            quote = today[today.symbol == position["symbol"]]
            if not quote.empty:
                q = quote.iloc[0]
                position["mark"] = float(q.close)
                if i >= position["exit_index"] and i > position["entry_index"] and not q.suspended and float(q.high) > float(q.lower_limit):
                    price = float(q.open) if float(q.open) > float(q.lower_limit) else None
                    if price:
                        proceeds = position["quantity"]*price*(1-(config["sell_cost_bps"]+config["slippage_bps"])/10000)
                        cash += proceeds
                        trades.append(dict(**position, exit_date=date, pnl=round(proceeds-position["cost"], 2), status="已平仓"))
                        position = None
        if pending:
            if position:
                trades.append(dict(symbol=pending["symbol"], date=pending["date"], status="资金占用，跳过"))
            else:
                quote = today[today.symbol == pending["symbol"]]
                if quote.empty or quote.iloc[0].suspended:
                    trades.append(dict(**pending, status="无报价或停牌，未成交"))
                else:
                    q = quote.iloc[0]
                    if float(q.open) >= float(q.upper_limit):
                        trades.append(dict(**pending, status="开盘涨停，保守不成交"))
                    else:
                        unit = float(q.open)*(1+(config["buy_cost_bps"]+config["slippage_bps"])/10000)
                        quantity = int(cash*config["position_pct"]/100/unit/config["lot_size"])*config["lot_size"]
                        if quantity:
                            cost = quantity*unit
                            cash -= cost
                            position = dict(symbol=pending["symbol"], signal_date=pending["date"], entry_date=date, entry_index=i, exit_index=i+horizon, quantity=quantity, cost=cost, mark=float(q.close))
                        else:
                            trades.append(dict(**pending, status="不足一手，未成交"))
            pending = None
        equity = cash + (position["quantity"]*position["mark"] if position else 0)
        curve.append(dict(date=date, equity=round(equity, 2)))
        pending = by_date.get(date)
    if position:
        trades.append(dict(**position, status="未平仓"))
    if pending:
        trades.append(dict(**pending, status="待下一交易日"))
    equities = np.array([r["equity"] for r in curve])
    max_dd = float(np.min(equities/np.maximum.accumulate(equities)-1)*100) if len(equities) else 0
    return dict(events=rows, summary=dict(samples=len(values), signals=len(rows), win_rate=round(sum(v > 0 for v in values)/len(values)*100, 2) if values else None, mean=round(float(np.mean(values)), 3) if values else None, median=round(float(np.median(values)), 3) if values else None), simulation=dict(trades=trades, curve=curve, max_drawdown=round(max_dd, 3), final_equity=curve[-1]["equity"] if curve else cash))
