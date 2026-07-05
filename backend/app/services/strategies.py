"""Four distinct, parameterized strategy templates on top of vectorbt indicators.

Each strategy function takes a close-price Series and returns (entries, exits) boolean
Series suitable for vbt.Portfolio.from_signals.
"""
import pandas as pd
import vectorbt as vbt


def sma_crossover(close: pd.Series, fast: int = 10, slow: int = 30):
    fast_ma = vbt.MA.run(close, fast)
    slow_ma = vbt.MA.run(close, slow)
    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)
    return entries, exits


def rsi_reversion(close: pd.Series, window: int = 14, low: int = 30, high: int = 70):
    rsi = vbt.RSI.run(close, window)
    entries = rsi.rsi_crossed_above(low)
    exits = rsi.rsi_crossed_above(high)
    return entries, exits


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
    "sma_crossover": {
        "label": "SMA Crossover",
        "fn": sma_crossover,
        "default_params": {"fast": 10, "slow": 30},
    },
    "rsi_reversion": {
        "label": "RSI Mean Reversion",
        "fn": rsi_reversion,
        "default_params": {"window": 14, "low": 30, "high": 70},
    },
    "momentum": {
        "label": "Time-Series Momentum",
        "fn": momentum,
        "default_params": {"lookback": 20, "threshold": 0.0},
    },
    "bollinger_reversion": {
        "label": "Bollinger Band Reversion",
        "fn": bollinger_reversion,
        "default_params": {"window": 20, "num_std": 2.0},
    },
}
