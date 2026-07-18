#!/usr/bin/env python3
"""Standalone quant strategy backtest CLI — 4 strategy templates, US + CN equities, vectorbt-driven.

No database, no API key. Fetches real OHLCV via yfinance (US) or akshare (CN, Sina-backed),
runs one of 4 parameterized strategies, and prints total return / Sharpe / max drawdown / win rate.

Extracted from quant-copilot's backtest engine (github.com/YunhaoDou/quant-copilot).
"""
import argparse
import itertools

import numpy as np
import pandas as pd
import vectorbt as vbt


def sma_crossover(close: pd.Series, fast: int = 10, slow: int = 30):
    fast_ma = vbt.MA.run(close, fast)
    slow_ma = vbt.MA.run(close, slow)
    return fast_ma.ma_crossed_above(slow_ma), fast_ma.ma_crossed_below(slow_ma)


def rsi_reversion(close: pd.Series, window: int = 14, low: int = 30, high: int = 70):
    rsi = vbt.RSI.run(close, window)
    return rsi.rsi_crossed_above(low), rsi.rsi_crossed_above(high)


def momentum(close: pd.Series, lookback: int = 20, threshold: float = 0.0):
    ret = close.pct_change(lookback)
    entries = (ret > threshold) & (ret.shift(1) <= threshold)
    exits = (ret < 0) & (ret.shift(1) >= 0)
    return entries.fillna(False), exits.fillna(False)


def bollinger_reversion(close: pd.Series, window: int = 20, num_std: float = 2.0):
    bb = vbt.BBANDS.run(close, window=window, alpha=num_std)
    entries = (close < bb.lower).fillna(False)
    exits = (close > bb.middle).fillna(False)
    return entries, exits


STRATEGIES = {
    "sma_crossover": {"label": "SMA Crossover", "fn": sma_crossover, "default_params": {"fast": 10, "slow": 30}},
    "rsi_reversion": {"label": "RSI Mean Reversion", "fn": rsi_reversion, "default_params": {"window": 14, "low": 30, "high": 70}},
    "momentum": {"label": "Time-Series Momentum", "fn": momentum, "default_params": {"lookback": 20, "threshold": 0.0}},
    "bollinger_reversion": {"label": "Bollinger Band Reversion", "fn": bollinger_reversion, "default_params": {"window": 20, "num_std": 2.0}},
}


def _safe_float(value) -> float:
    value = float(value)
    return 0.0 if np.isnan(value) or np.isinf(value) else value


def fetch_us(ticker: str, start: str, end: str) -> pd.Series:
    import yfinance as yf

    df = yf.Ticker(ticker.upper()).history(start=start, end=end, auto_adjust=True)
    if df.empty:
        raise ValueError(f"no data for US ticker {ticker}")
    return df["Close"].rename(ticker.upper())


def _guess_exchange(code: str) -> str:
    # Shanghai: 60/68/9x ; Shenzhen: 00/30
    return f"sh{code}" if code.startswith(("6", "9")) else f"sz{code}"


def fetch_cn(code: str, start: str, end: str) -> pd.Series:
    import akshare as ak

    symbol = code if code.startswith(("sh", "sz")) else _guess_exchange(code)
    df = ak.stock_zh_a_daily(
        symbol=symbol,
        start_date=start.replace("-", ""),
        end_date=end.replace("-", ""),
        adjust="qfq",
    )
    if df.empty:
        raise ValueError(f"no data for CN code {code}")
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")["close"].rename(symbol)


def run_single(close: pd.Series, strategy_key: str, params: dict | None = None) -> dict:
    spec = STRATEGIES[strategy_key]
    merged = {**spec["default_params"], **(params or {})}
    entries, exits = spec["fn"](close, **merged)
    pf = vbt.Portfolio.from_signals(close, entries, exits, init_cash=100_000.0, fees=0.001, freq="1D")
    return {
        "strategy": spec["label"],
        "params": merged,
        "total_return": _safe_float(pf.total_return()),
        "sharpe_ratio": _safe_float(pf.sharpe_ratio()),
        "max_drawdown": _safe_float(pf.max_drawdown()),
        "win_rate": _safe_float(pf.trades.win_rate()) if pf.trades.count() > 0 else 0.0,
        "num_trades": int(pf.trades.count()),
    }


def print_table(rows: list[dict]) -> None:
    header = f"{'strategy':<26}{'params':<28}{'return':>10}{'sharpe':>10}{'maxDD':>10}{'winRate':>10}{'trades':>8}"
    print(header)
    print("-" * len(header))
    for r in rows:
        params_str = ",".join(f"{k}={v}" for k, v in r["params"].items())
        print(
            f"{r['strategy']:<26}{params_str:<28}"
            f"{r['total_return'] * 100:>9.1f}%{r['sharpe_ratio']:>10.2f}"
            f"{r['max_drawdown'] * 100:>9.1f}%{r['win_rate'] * 100:>9.1f}%{r['num_trades']:>8}"
        )


def buy_and_hold_return(close: pd.Series) -> float:
    return _safe_float(close.iloc[-1] / close.iloc[0] - 1)


def print_verdict(rows: list[dict], bh_return: float) -> None:
    print(f"\n买入持有基准：{bh_return * 100:.1f}%\n")
    print(f"{'strategy':<26}{'vs buy-and-hold':<20}{'verdict'}")
    print("-" * 70)
    for r in rows:
        edge = r["total_return"] - bh_return
        beats = edge > 0
        verdict = "跑赢基准" if beats else "跑不赢，别信"
        print(f"{r['strategy']:<26}{edge * 100:>+8.1f}pt{'':<10}{verdict}")


def main():
    parser = argparse.ArgumentParser(description="Quant strategy backtest — US + CN equities, vectorbt-driven")
    parser.add_argument("--market", choices=["us", "cn"], required=True)
    parser.add_argument("--ticker", required=True, help="US: AAPL. CN: 600519 (exchange auto-detected) or sh600519/sz000001")
    parser.add_argument("--start", default="2014-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--strategy", choices=list(STRATEGIES), help="omit to compare all 4")
    parser.add_argument("--sweep", nargs="*", help="param=v1,v2,v3 ... requires --strategy")
    parser.add_argument("--vs-buyhold", action="store_true", help="compare against buy-and-hold, print a verdict per strategy")
    args = parser.parse_args()

    close = (fetch_us if args.market == "us" else fetch_cn)(args.ticker, args.start, args.end)
    print(f"{args.ticker} · {len(close)} bars · {close.index[0].date()} -> {close.index[-1].date()}\n")

    if args.sweep:
        if not args.strategy:
            parser.error("--sweep requires --strategy")
        grid = {}
        for spec in args.sweep:
            key, values = spec.split("=")
            grid[key] = [int(v) if v.lstrip("-").isdigit() else float(v) for v in values.split(",")]
        keys = list(grid.keys())
        rows = [run_single(close, args.strategy, dict(zip(keys, combo))) for combo in itertools.product(*grid.values())]
    elif args.strategy:
        rows = [run_single(close, args.strategy)]
    else:
        rows = [run_single(close, key) for key in STRATEGIES]

    print_table(rows)
    if args.vs_buyhold:
        print_verdict(rows, buy_and_hold_return(close))


if __name__ == "__main__":
    main()
