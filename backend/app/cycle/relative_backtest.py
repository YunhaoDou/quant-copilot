"""A股「相对强势趋势」规则的历史回测（仅价量规则版）。

口径与策略中心的前向模拟保持一致（backend/app/cycle/strategy_center.py evaluate）：
    入场：收盘价 > 前 20 日收盘高点（不含当日），收盘价 > MA20，MA20 > MA60，
          60 个交易日相对沪深300ETF的超额收益 >= research_relative_min_pp。
    出场：收盘价 < MA20，或 MA20 < MA60，或相对超额重新跌破门槛。

刻意不包含的部分（前向账户才有，回测不还原，避免把不可成交收益当成规则收益）：
    * 共用止损/止盈/最大回撤/时间退出
    * T+1、涨跌停排队、整手、盘口容量
    * 历史成分与财务快照（本规则不需要）

因此结果只用于检验规则本身，不代表可成交收益，也不计入前向模拟账户业绩。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

STRATEGY_KEY = "relative_trend_ashare"
LABEL = "相对强势趋势（A股规则回测）"
MIN_BARS = 80


def _safe_float(value) -> float:
    value = float(value)
    return 0.0 if np.isnan(value) or np.isinf(value) else value


def _series(frame: pd.DataFrame, column: str = "close") -> pd.Series:
    ordered = frame.sort_values("trade_date")
    return pd.Series(
        ordered[column].astype(float).values,
        index=pd.DatetimeIndex(ordered["trade_date"]),
    )


def run_relative_trend(
    frame: pd.DataFrame,
    benchmark_frame: pd.DataFrame,
    min_pp: float,
    *,
    init_cash: float = 100_000.0,
    fees: float = 0.001,
) -> dict:
    """把「相对强势趋势」规则在给定日线上跑一遍，返回与 backtest_engine 一致的结果结构。"""
    close = _series(frame)
    if len(close) < MIN_BARS:
        raise ValueError(f"相对强势趋势回测至少需要 {MIN_BARS} 根日线，当前 {len(close)} 根")

    benchmark = _series(benchmark_frame).reindex(close.index).ffill()
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()
    high20_prior = close.shift(1).rolling(20).max()  # 不含当日，避免用当日收盘判当日突破
    relative_pp = (
        (close / close.shift(60) - 1.0) - (benchmark / benchmark.shift(60) - 1.0)
    ) * 100.0  # 百分点

    entries = (
        (close > high20_prior) & (close > ma20) & (ma20 > ma60) & (relative_pp >= min_pp)
    )
    exits = (close < ma20) | (ma20 < ma60) | (relative_pp < min_pp)
    entries = entries.fillna(False).astype(bool)
    exits = exits.fillna(False).astype(bool)

    import vectorbt as vbt
    portfolio = vbt.Portfolio.from_signals(
        close, entries, exits, init_cash=init_cash, fees=fees, freq="1D"
    )
    trade_count = int(portfolio.trades.count())
    return {
        "strategy_key": STRATEGY_KEY,
        "label": LABEL,
        "params": {"min_relative_pp": min_pp, "high_lookback": 20, "trend_ma": "20/60", "relative_lookback": 60},
        "total_return": _safe_float(portfolio.total_return()),
        "sharpe_ratio": _safe_float(portfolio.sharpe_ratio()),
        "max_drawdown": _safe_float(portfolio.max_drawdown()),
        "win_rate": _safe_float(portfolio.trades.win_rate()) if trade_count > 0 else 0.0,
        "num_trades": trade_count,
        "equity_curve": portfolio.value(),
        "bars": int(len(close)),
        "data_through": str(close.index[-1].date()),
        "note": "仅价量规则回测；不含共用风控、T+1、涨跌停与整手约束，不代表可成交收益。",
    }
