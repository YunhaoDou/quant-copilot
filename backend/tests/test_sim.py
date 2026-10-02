"""Systematic-simulation tests. Price history is seeded directly (no network) so signal
generation, reconciliation, equity logging, and the report are deterministic."""
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import select

from app.models import PaperAccount, Price, SimEquity, Ticker
from app.services import sim

# Most test functions are async, so the module-level marker covers them;
# the three pure-signal tests are sync and will get a harmless warning only.


async def _seed_series(session, symbol, closes, start=date(2026, 1, 1)):
    session.add(Ticker(symbol=symbol, name=f"{symbol} Inc.", market="US"))
    await session.flush()
    for i, px in enumerate(closes):
        session.add(
            Price(ticker_symbol=symbol, trade_date=start + timedelta(days=i), open=px, high=px, low=px, close=px, volume=1.0)
        )
    await session.commit()


# ---- Pure-signal tests ----
def test_momentum_long_on_a_jump():
    """Momentum (20-d ret crosses 0 from below) fires after a sharp price jump."""
    close = pd.Series([100.0] * 40 + [130.0] * 2, index=pd.date_range("2026-01-01", periods=42))
    assert sim.current_target_long(close, "momentum") is True


def test_momentum_flat_when_lookback_not_warm():
    """Monotonic rise keeps 20-d ret always positive — no crossover entry fires."""
    close = pd.Series(range(100, 140), index=pd.date_range("2026-01-01", periods=40))
    assert sim.current_target_long(close, "momentum") is False


def test_sma_crossover_long_on_v_recovery():
    """SMA 10/30 crosses above when price comes off a trough."""
    v = np.concatenate([np.linspace(100, 50, 50), np.linspace(50, 120, 50)])
    close = pd.Series(v, index=pd.date_range("2026-01-01", periods=100))
    assert sim.current_target_long(close, "sma_crossover") is True


def test_short_history_is_flat():
    close = pd.Series([100.0], index=pd.date_range("2026-01-01", periods=1))
    assert sim.current_target_long(close, "sma_crossover") is False


async def test_init_sim_creates_accounts_and_benchmark_holds_spy(db_session):
    await _seed_series(db_session, "SPY", [400.0] * 5)
    result = await sim.init_sim(db_session, starting_cash=1000.0)
    assert sim.BENCHMARK_ACCOUNT in result["created"]
    assert "sim-momentum" in result["created"]

    # benchmark should have bought SPY: floor(1000/400) = 2 shares -> 800 invested, 200 cash
    bench = (
        await db_session.execute(select(PaperAccount).where(PaperAccount.name == sim.BENCHMARK_ACCOUNT))
    ).scalar_one()
    snap = await sim.paper_trading.account_snapshot(db_session, bench.id)
    assert snap["positions"] and snap["positions"][0]["symbol"] == "SPY"
    assert snap["positions"][0]["quantity"] == 2

    # idempotent: re-init creates nothing new
    again = await sim.init_sim(db_session, starting_cash=1000.0)
    assert again["created"] == []


async def test_run_sim_day_logs_equity_for_all_accounts(db_session):
    await _seed_series(db_session, "SPY", [400.0] * 40)
    # AAPL rising -> momentum & others may go long; enough bars for indicators
    await _seed_series(db_session, "AAPL", list(range(100, 140)))
    await sim.init_sim(db_session, starting_cash=1000.0)

    out = await sim.run_sim_day(db_session, on_date=date(2026, 3, 1))
    # 4 strategy accounts + benchmark = 5 equity rows for this date
    rows = (
        await db_session.execute(select(SimEquity).where(SimEquity.trade_date == date(2026, 3, 1)))
    ).scalars().all()
    assert len(rows) == 5
    assert set(out["equities"].keys()) >= {"sim-momentum", sim.BENCHMARK_ACCOUNT}

    # re-running the same day must not create duplicate rows (upsert) or double-trade
    await sim.run_sim_day(db_session, on_date=date(2026, 3, 1))
    rows2 = (
        await db_session.execute(select(SimEquity).where(SimEquity.trade_date == date(2026, 3, 1)))
    ).scalars().all()
    assert len(rows2) == 5


async def test_sim_report_ranks_and_computes_vs_spy(db_session):
    await _seed_series(db_session, "SPY", [400.0] * 40)
    await _seed_series(db_session, "AAPL", list(range(100, 140)))
    await sim.init_sim(db_session, starting_cash=1000.0)
    await sim.run_sim_day(db_session, on_date=date(2026, 3, 1))

    report = await sim.sim_report(db_session)
    assert report["benchmark"]["account"] == sim.BENCHMARK_ACCOUNT
    assert len(report["strategies"]) == 4
    # ranked descending by return
    returns = [s["total_return_pct"] for s in report["strategies"]]
    assert returns == sorted(returns, reverse=True)
    # vs_spy delta is present for every strategy
    assert all(s["vs_spy_pct"] is not None for s in report["strategies"])
