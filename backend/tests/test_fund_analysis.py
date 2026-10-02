"""compute_metrics is pure (synthetic series, deterministic, no network — same style as
test_fund_flow.py). Premium/discount snapshot needs live AKShare spot data so it's tested
against the real endpoint (matches this project's real-data testing convention).
"""
from datetime import date, timedelta

import pandas as pd
import pytest

from app.services import fund_analysis


def _nav_series(prices: list[float]) -> pd.Series:
    base = date(2026, 1, 1)
    idx = pd.DatetimeIndex([base + timedelta(days=i) for i in range(len(prices))])
    return pd.Series(prices, index=idx)


def test_compute_metrics_steady_uptrend():
    series = _nav_series([1.0 + 0.01 * i for i in range(60)])
    m = fund_analysis.compute_metrics(series)
    assert m["total_return"] > 0
    assert m["annualized_return"] > 0
    assert m["max_drawdown"] == 0.0  # monotonic uptrend, never below its own running max
    assert m["win_rate"] == 100.0


def test_compute_metrics_steady_downtrend():
    series = _nav_series([2.0 - 0.01 * i for i in range(60)])
    m = fund_analysis.compute_metrics(series)
    assert m["total_return"] < 0
    assert m["max_drawdown"] < 0
    assert m["win_rate"] == 0.0


def test_compute_metrics_insufficient_history_returns_zeros():
    m = fund_analysis.compute_metrics(_nav_series([1.0]))
    assert m == {
        "total_return": 0.0, "annualized_return": 0.0, "volatility": 0.0,
        "sharpe_ratio": 0.0, "max_drawdown": 0.0, "win_rate": 0.0, "window_days": 1,
    }


def test_assess_alert_thresholds():
    assert fund_analysis._assess_alert(0.0)[0] == fund_analysis.LEVEL_NORMAL
    assert fund_analysis._assess_alert(2.0)[0] == fund_analysis.LEVEL_WARNING
    assert fund_analysis._assess_alert(4.0)[0] == fund_analysis.LEVEL_DANGER
    assert fund_analysis._assess_alert(-2.0)[0] == fund_analysis.LEVEL_WARNING
    assert fund_analysis._assess_alert(-4.0)[0] == fund_analysis.LEVEL_DANGER


@pytest.mark.asyncio
async def test_get_premium_snapshot_real_etf():
    snapshot = fund_analysis.get_premium_snapshot("513330", "ETF")
    assert snapshot is not None
    assert snapshot.code == "513330"
    assert snapshot.iopv > 0
    assert snapshot.alert_level in (
        fund_analysis.LEVEL_NORMAL, fund_analysis.LEVEL_WARNING, fund_analysis.LEVEL_DANGER
    )
