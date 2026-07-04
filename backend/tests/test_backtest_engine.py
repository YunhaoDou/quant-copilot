"""Backtest engine tests against real 11-year A-share history (no mocking price data —
the whole point of this bullet is that the numbers are computed from real market data)."""
import pandas as pd
import pytest

from app.services import data_ingestion
from app.services.backtest_engine import run_comparison, run_param_sweep
from app.services.strategies import STRATEGIES

TICKER = "600519"  # Kweichow Moutai — liquid, long real history


@pytest.fixture(scope="module")
def real_close_series() -> pd.Series:
    df = data_ingestion.fetch_history(TICKER, start="20140101", end="20251231")
    assert len(df) > 2500, "expected ~11 years of daily bars"
    return df.set_index(pd.DatetimeIndex(df["trade_date"]))["close"]


def test_all_four_strategies_are_distinct_and_nondegenerate(real_close_series):
    results = run_comparison(real_close_series)
    assert {r["strategy_key"] for r in results} == set(STRATEGIES)

    metrics_seen = set()
    for r in results:
        assert r["num_trades"] > 0, f"{r['strategy_key']} produced zero trades on 11y of real data"
        assert len(r["equity_curve"]) == len(real_close_series)
        metrics_seen.add(round(r["total_return"], 6))

    # 4 distinct strategies on the same data must not all land on the same return
    assert len(metrics_seen) == 4


def test_param_sweep_changes_output(real_close_series):
    results = run_param_sweep(real_close_series, "sma_crossover", {"fast": [5, 10], "slow": [30, 60]})
    assert len(results) == 4
    returns = {r["total_return"] for r in results}
    assert len(returns) > 1, "sweeping fast/slow should not all converge to one identical return"
