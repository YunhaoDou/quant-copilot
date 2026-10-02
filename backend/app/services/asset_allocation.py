"""Macro-regime asset-allocation Agent — an intentionally simple 2-factor approximation
of the Merrill-clock idea (growth x inflation -> regime -> stock/bond mix), NOT a full
macro model. A true investment clock needs GDP growth and CPI inflation series, which
require a FRED API key/registration this platform doesn't have. Instead:

  - growth proxy: SPY price vs its own 200-day moving average (up = expansion, down = contraction)
  - inflation/rate-expectations proxy: 10Y Treasury yield (^TNX) trend over the last ~3
    months (rising yields ~ tightening/inflation pressure, falling ~ easing)

Both series come from yfinance (already a dependency, no new API key), fetched fresh each
call — this reads the whole market, not a specific ticker, so there's nothing to persist
per-symbol; it's cheap to recompute, same rationale as services/risk.py.
"""
from datetime import date, timedelta

import pandas as pd

from app.services.data_ingestion import fetch_history

GROWTH_WINDOW = 200
RATE_LOOKBACK = 63
FETCH_LOOKBACK_DAYS = 450  # calendar days of buffer so 200 trading days + 63-day delta always fit
METHOD = "spy_200ma_x_10y_trend_v1"
DISCLAIMER = (
    "Approximation using SPY price trend and 10Y Treasury yield trend only — not a full "
    "macro model (no GDP growth or CPI inflation data). Not investment advice."
)

# (growth_trend, rate_trend) -> (regime, suggested_stock_pct, suggested_bond_pct)
REGIME_TABLE = {
    ("up", "falling"): ("recovery", 75, 25),
    ("up", "rising"): ("overheat", 55, 45),
    ("down", "rising"): ("stagflation", 30, 70),
    ("down", "falling"): ("reflation", 45, 55),
}


def _growth_trend(spy_close: pd.Series) -> tuple[str, float]:
    if len(spy_close) < GROWTH_WINDOW:
        raise ValueError(f"need at least {GROWTH_WINDOW} trading days of SPY history, got {len(spy_close)}")
    ma = spy_close.tail(GROWTH_WINDOW).mean()
    if ma == 0:
        raise ValueError("SPY 200-day average is zero — bad data")
    pct = float((spy_close.iloc[-1] - ma) / ma)
    return ("up" if pct > 0 else "down"), pct


def _rate_trend(tnx_close: pd.Series, lookback: int = RATE_LOOKBACK) -> tuple[str, float]:
    if len(tnx_close) < lookback + 1:
        raise ValueError(f"need at least {lookback + 1} trading days of 10Y yield history, got {len(tnx_close)}")
    delta = float(tnx_close.iloc[-1] - tnx_close.iloc[-1 - lookback])
    return ("rising" if delta > 0 else "falling"), delta


def compute_regime(spy_close: pd.Series, tnx_close: pd.Series, irx_close: pd.Series | None = None) -> dict:
    """Pure function: SPY/10Y (/13-week, optional) close series -> regime read. Testable
    without any network call."""
    growth_trend, spy_vs_200ma_pct = _growth_trend(spy_close)
    rate_trend, yield_delta = _rate_trend(tnx_close)
    regime, stock_pct, bond_pct = REGIME_TABLE[(growth_trend, rate_trend)]

    yield_10y = float(tnx_close.iloc[-1])
    yield_3m = float(irx_close.iloc[-1]) if irx_close is not None and len(irx_close) else None
    yield_curve_spread = round(yield_10y - yield_3m, 4) if yield_3m is not None else None

    return {
        "as_of_date": spy_close.index[-1].date().isoformat(),
        "regime": regime,
        "growth_trend": growth_trend,
        "rate_trend": rate_trend,
        "spy_vs_200ma_pct": round(spy_vs_200ma_pct, 4),
        "yield_10y": round(yield_10y, 4),
        "yield_3m": round(yield_3m, 4) if yield_3m is not None else None,
        "yield_curve_spread": yield_curve_spread,
        "yield_10y_change_63d": round(yield_delta, 4),
        "suggested_stock_pct": stock_pct,
        "suggested_bond_pct": bond_pct,
        "etf_recommendation": {"equity": "SPY", "bond": "IEF"},
        "method": METHOD,
        "disclaimer": DISCLAIMER,
    }


def _close_series(symbol: str, start: str) -> pd.Series:
    df = fetch_history(symbol, start=start)
    if df.empty:
        return pd.Series(dtype=float)
    return pd.Series(df["close"].values, index=pd.DatetimeIndex(df["trade_date"]), name=symbol)


def get_asset_allocation() -> dict:
    start = (date.today() - timedelta(days=FETCH_LOOKBACK_DAYS)).isoformat()
    spy_close = _close_series("SPY", start)
    tnx_close = _close_series("^TNX", start)
    irx_close = _close_series("^IRX", start)
    if spy_close.empty or tnx_close.empty:
        raise ValueError("could not fetch SPY/^TNX history from yfinance")
    return compute_regime(spy_close, tnx_close, irx_close)
