"""M5 risk-panel tests. Positions and price history are seeded directly (no network),
so exposure / concentration / drawdown / alert logic is deterministic."""
from datetime import date, timedelta

import pytest

from app.models import PaperPosition, Price, Ticker
from app.services import paper_trading, risk

pytestmark = pytest.mark.asyncio


async def _seed_ticker(session, symbol, close):
    session.add(Ticker(symbol=symbol, name=f"{symbol} Inc.", market="US"))
    await session.flush()
    session.add(
        Price(ticker_symbol=symbol, trade_date=date(2026, 1, 5), open=close, high=close, low=close, close=close, volume=1.0)
    )
    await session.commit()


async def _add_position(session, account_id, symbol, qty, avg_cost):
    session.add(PaperPosition(account_id=account_id, ticker_symbol=symbol, quantity=qty, avg_cost=avg_cost))
    await session.commit()


async def test_exposure_and_concentration_two_positions(db_session):
    await _seed_ticker(db_session, "AAA", 100.0)
    await _seed_ticker(db_session, "BBB", 100.0)
    acct = await paper_trading.open_account(db_session, "risk1", 10_000.0)
    # 60 AAA @100 = 6000, 30 BBB @100 = 3000 -> positions 9000, cash 1000, equity 10000
    acct.cash_balance = 1000.0
    await _add_position(db_session, acct.id, "AAA", 60, 100.0)
    await _add_position(db_session, acct.id, "BBB", 30, 100.0)

    snap = await risk.risk_snapshot(db_session, acct.id)
    assert snap["equity"] == 10_000.0
    assert snap["gross_exposure"] == 9_000.0
    assert snap["cash_pct"] == pytest.approx(0.10, abs=1e-6)
    assert snap["num_positions"] == 2
    # weights within book: 6000/9000, 3000/9000 -> HHI = (2/3)^2 + (1/3)^2 = 0.5556
    assert snap["hhi"] == pytest.approx(0.5556, abs=1e-3)
    assert snap["largest_position_weight"] == pytest.approx(0.60, abs=1e-3)  # AAA is 60% of equity


async def test_concentration_alert_fires_on_single_big_position(db_session):
    await _seed_ticker(db_session, "AAA", 100.0)
    acct = await paper_trading.open_account(db_session, "risk2", 10_000.0)
    acct.cash_balance = 1000.0
    await _add_position(db_session, acct.id, "AAA", 90, 100.0)  # 9000 -> 90% of 10000 equity

    snap = await risk.risk_snapshot(db_session, acct.id)
    codes = {a["code"] for a in snap["alerts"]}
    assert "concentration" in codes  # 90% > 40% limit
    assert snap["effective_positions"] == 1.0  # single holding, HHI = 1


async def test_low_cash_alert(db_session):
    await _seed_ticker(db_session, "AAA", 100.0)
    acct = await paper_trading.open_account(db_session, "risk3", 10_000.0)
    acct.cash_balance = 100.0  # 1% cash
    await _add_position(db_session, acct.id, "AAA", 99, 100.0)  # 9900
    snap = await risk.risk_snapshot(db_session, acct.id)
    assert "low_cash" in {a["code"] for a in snap["alerts"]}


async def test_drawdown_computed_from_price_history(db_session):
    # AAA price path: 100 -> 150 -> 75 (drop from peak 150 to 75 = -50%)
    session = db_session
    session.add(Ticker(symbol="AAA", name="AAA Inc.", market="US"))
    await session.flush()
    base = date(2025, 1, 1)
    for i, px in enumerate([100.0, 150.0, 75.0]):
        session.add(
            Price(ticker_symbol="AAA", trade_date=base + timedelta(days=i), open=px, high=px, low=px, close=px, volume=1.0)
        )
    await session.commit()

    acct = await paper_trading.open_account(db_session, "risk4", 10_000.0)
    acct.cash_balance = 0.0  # pure equity so drawdown is undamped by cash
    await _add_position(db_session, acct.id, "AAA", 10, 100.0)

    snap = await risk.risk_snapshot(db_session, acct.id)
    assert snap["drawdown"]["max_drawdown"] == pytest.approx(-0.50, abs=1e-3)
    assert snap["drawdown"]["window_days"] == 3
    assert "drawdown" in {a["code"] for a in snap["alerts"]}  # -50% < -20% limit


async def test_empty_account_has_no_alerts(db_session):
    acct = await paper_trading.open_account(db_session, "risk5", 10_000.0)
    snap = await risk.risk_snapshot(db_session, acct.id)
    assert snap["gross_exposure"] == 0.0
    assert snap["num_positions"] == 0
    assert snap["alerts"] == []
    assert snap["drawdown"]["max_drawdown"] == 0.0
