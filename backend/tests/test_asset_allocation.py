"""Asset-allocation tests. All four regime-table branches are exercised with hand-derived
synthetic SPY/10Y series (no network — get_asset_allocation's yfinance call is the only
untested part, by design, since it's a thin fetch wrapper around already-tested fetch_history)."""
from datetime import date, timedelta

import pandas as pd
import pytest

from app.services.asset_allocation import (
    REGIME_TABLE,
    _growth_trend,
    _rate_trend,
    compute_regime,
)


def _series(values: list[float], start: date = date(2025, 1, 1)) -> pd.Series:
    idx = pd.DatetimeIndex([start + timedelta(days=i) for i in range(len(values))])
    return pd.Series(values, index=idx)


# ---- _growth_trend ----

def test_growth_trend_up_hand_computed():
    # 199 values at 100, last at 110 -> ma200 = (199*100+110)/200 = 100.05 -> pct > 0 -> "up"
    closes = _series([100.0] * 199 + [110.0])
    trend, pct = _growth_trend(closes)
    assert trend == "up"
    assert pct == pytest.approx((110.0 - 100.05) / 100.05, abs=1e-9)


def test_growth_trend_down_hand_computed():
    closes = _series([100.0] * 199 + [90.0])
    trend, pct = _growth_trend(closes)
    assert trend == "down"
    assert pct < 0


def test_growth_trend_insufficient_history_raises():
    closes = _series([100.0] * 50)
    with pytest.raises(ValueError, match="need at least 200"):
        _growth_trend(closes)


# ---- _rate_trend ----

def test_rate_trend_rising_hand_computed():
    # 64 values: index -1-63=0 is 4.0, index -1=63 is 4.5 -> delta = +0.5 -> "rising"
    closes = _series([4.0] + [4.2] * 62 + [4.5])
    trend, delta = _rate_trend(closes)
    assert trend == "rising"
    assert delta == pytest.approx(0.5, abs=1e-9)


def test_rate_trend_falling_hand_computed():
    closes = _series([4.5] + [4.2] * 62 + [4.0])
    trend, delta = _rate_trend(closes)
    assert trend == "falling"
    assert delta == pytest.approx(-0.5, abs=1e-9)


def test_rate_trend_insufficient_history_raises():
    closes = _series([4.0] * 10)
    with pytest.raises(ValueError, match="need at least 64"):
        _rate_trend(closes)


# ---- compute_regime: all four quadrants of the regime table ----

def _spy(growth_up: bool) -> pd.Series:
    return _series([100.0] * 199 + [110.0 if growth_up else 90.0])


def test_regime_recovery_up_growth_falling_rates():
    spy = _spy(growth_up=True)
    tnx = _series([4.5] + [4.2] * 62 + [4.0])  # falling
    result = compute_regime(spy, tnx)
    assert result["growth_trend"] == "up"
    assert result["rate_trend"] == "falling"
    assert result["regime"] == "recovery"
    assert (result["suggested_stock_pct"], result["suggested_bond_pct"]) == REGIME_TABLE[("up", "falling")][1:]


def test_regime_overheat_up_growth_rising_rates():
    spy = _spy(growth_up=True)
    tnx = _series([4.0] + [4.2] * 62 + [4.5])  # rising
    result = compute_regime(spy, tnx)
    assert result["regime"] == "overheat"
    assert result["suggested_stock_pct"] == 55
    assert result["suggested_bond_pct"] == 45


def test_regime_stagflation_down_growth_rising_rates():
    spy = _spy(growth_up=False)
    tnx = _series([4.0] + [4.2] * 62 + [4.5])  # rising
    result = compute_regime(spy, tnx)
    assert result["regime"] == "stagflation"
    assert result["suggested_stock_pct"] == 30
    assert result["suggested_bond_pct"] == 70


def test_regime_reflation_down_growth_falling_rates():
    spy = _spy(growth_up=False)
    tnx = _series([4.5] + [4.2] * 62 + [4.0])  # falling
    result = compute_regime(spy, tnx)
    assert result["regime"] == "reflation"
    assert result["suggested_stock_pct"] == 45
    assert result["suggested_bond_pct"] == 55


def test_regime_table_covers_all_four_combinations():
    assert set(REGIME_TABLE) == {("up", "falling"), ("up", "rising"), ("down", "rising"), ("down", "falling")}
    regimes = {v[0] for v in REGIME_TABLE.values()}
    assert regimes == {"recovery", "overheat", "stagflation", "reflation"}
    # stock/bond suggestions always sum to 100
    for _regime, stock_pct, bond_pct in REGIME_TABLE.values():
        assert stock_pct + bond_pct == 100


def test_yield_curve_spread_hand_computed():
    spy = _spy(growth_up=True)
    tnx = _series([4.0] + [4.2] * 62 + [4.5])
    irx = _series([3.0] * 64)
    result = compute_regime(spy, tnx, irx)
    assert result["yield_10y"] == pytest.approx(4.5, abs=1e-9)
    assert result["yield_3m"] == pytest.approx(3.0, abs=1e-9)
    assert result["yield_curve_spread"] == pytest.approx(1.5, abs=1e-9)


def test_yield_curve_spread_none_without_irx():
    spy = _spy(growth_up=True)
    tnx = _series([4.0] + [4.2] * 62 + [4.5])
    result = compute_regime(spy, tnx, irx_close=None)
    assert result["yield_3m"] is None
    assert result["yield_curve_spread"] is None


def test_disclaimer_and_method_present():
    spy = _spy(growth_up=True)
    tnx = _series([4.0] + [4.2] * 62 + [4.5])
    result = compute_regime(spy, tnx)
    assert "approximation" in result["disclaimer"].lower()
    assert result["method"] == "spy_200ma_x_10y_trend_v1"
    assert result["etf_recommendation"] == {"equity": "SPY", "bond": "IEF"}
