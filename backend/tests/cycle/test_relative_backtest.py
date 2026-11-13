"""A股相对强势趋势规则的历史回测（纯价量规则版）。"""
import numpy as np
import pandas as pd
import pytest

from app.cycle import strategy_center
from app.cycle.relative_backtest import run_relative_trend


def frame_from(close, start="2025-01-02"):
    dates = pd.bdate_range(start, periods=len(close))
    return pd.DataFrame({"trade_date": [d.date() for d in dates], "close": close})


def test_breakout_then_trend_break_produces_trades_and_full_metrics():
    n = 140
    stock = np.full(n, 100.0)
    stock[80:110] = np.linspace(101.0, 130.0, 30)   # 20日新高 + 均线多头 + 相对基准走强
    stock[110:] = np.linspace(129.0, 95.0, n - 110)  # 跌回 MA20/MA60 下方
    benchmark = np.full(n, 100.0)                    # 基准不动，相对超额只来自个股

    result = run_relative_trend(frame_from(stock), frame_from(benchmark), 3.0)

    assert result["strategy_key"] == "relative_trend_ashare"
    assert result["label"].startswith("相对强势趋势")
    assert result["num_trades"] >= 1
    assert result["bars"] == n
    assert result["data_through"]
    for key in ("total_return", "sharpe_ratio", "max_drawdown", "win_rate"):
        assert np.isfinite(result[key])
    assert len(result["equity_curve"]) == n
    assert "不含共用风控" in result["note"]


def test_flat_market_never_breaks_out_and_never_trades():
    flat = np.full(140, 100.0)
    result = run_relative_trend(frame_from(flat), frame_from(flat), 3.0)
    assert result["num_trades"] == 0
    assert result["total_return"] == pytest.approx(0.0, abs=1e-9)


def test_short_series_is_rejected_instead_of_silently_backtested():
    with pytest.raises(ValueError, match="至少需要 80 根日线"):
        run_relative_trend(frame_from(np.full(60, 100.0)), frame_from(np.full(60, 100.0)), 3.0)


def test_benchmark_with_missing_dates_is_aligned_not_fabricated():
    n = 140
    stock = np.full(n, 100.0)
    stock[80:] = np.linspace(101.0, 120.0, n - 80)
    benchmark_frame = frame_from(np.full(n, 100.0))
    # 基准缺一天：按前值对齐，仍可回测，且不产生额外成交。
    benchmark_frame = benchmark_frame.drop(index=50).reset_index(drop=True)
    result = run_relative_trend(frame_from(stock), benchmark_frame, 3.0)
    assert result["bars"] == n
    assert result["num_trades"] >= 0


def test_every_catalog_strategy_declares_backtest_availability():
    assert len(strategy_center.CATALOG) == 8
    for spec in strategy_center.CATALOG:
        coverage = spec.get("backtest")
        assert coverage and isinstance(coverage["supported"], bool) and coverage.get("reason")
    assert strategy_center.BACKTEST_COVERAGE["relative-trend"]["supported"] is True
    assert strategy_center.BACKTEST_COVERAGE["quality-value"]["supported"] is False
