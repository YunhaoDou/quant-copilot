"""M4 paper-trading engine tests. Prices are seeded directly (no network) so the
order-execution and P&L math is deterministic."""
from datetime import date

import pytest

from app.models import Price, Ticker
from app.services import paper_trading
from app.services.paper_trading import OrderError

pytestmark = pytest.mark.asyncio


async def _seed_symbol(session, symbol="AAPL", close=100.0):
    session.add(Ticker(symbol=symbol, name=f"{symbol} Inc.", market="US"))
    await session.flush()  # ticker must exist before price FK
    session.add(
        Price(ticker_symbol=symbol, trade_date=date(2026, 1, 5), open=close, high=close, low=close, close=close, volume=1_000_000.0)
    )
    await session.commit()


async def test_market_buy_updates_cash_and_position(db_session):
    await _seed_symbol(db_session, close=100.0)
    acct = await paper_trading.open_account(db_session, "main", 10_000.0)

    order = await paper_trading.place_order(db_session, acct.id, "AAPL", "buy", 20)
    assert order.status == "filled"
    assert order.fill_price == 100.0

    snap = await paper_trading.account_snapshot(db_session, acct.id)
    assert snap["cash_balance"] == 8_000.0  # 10000 - 20*100
    assert snap["positions"][0]["quantity"] == 20
    assert snap["positions"][0]["avg_cost"] == 100.0
    assert snap["total_equity"] == 10_000.0  # cash 8000 + 20*100


async def test_insufficient_cash_rejected(db_session):
    await _seed_symbol(db_session, close=100.0)
    acct = await paper_trading.open_account(db_session, "small", 500.0)
    order = await paper_trading.place_order(db_session, acct.id, "AAPL", "buy", 20)  # needs 2000
    assert order.status == "rejected"
    assert "insufficient cash" in order.reason
    snap = await paper_trading.account_snapshot(db_session, acct.id)
    assert snap["cash_balance"] == 500.0  # untouched


async def test_sell_realizes_cash_and_insufficient_shares_rejected(db_session):
    await _seed_symbol(db_session, close=100.0)
    acct = await paper_trading.open_account(db_session, "seller", 10_000.0)
    await paper_trading.place_order(db_session, acct.id, "AAPL", "buy", 10)

    oversell = await paper_trading.place_order(db_session, acct.id, "AAPL", "sell", 50)
    assert oversell.status == "rejected"
    assert "insufficient shares" in oversell.reason

    sell = await paper_trading.place_order(db_session, acct.id, "AAPL", "sell", 10)
    assert sell.status == "filled"
    snap = await paper_trading.account_snapshot(db_session, acct.id)
    assert snap["cash_balance"] == 10_000.0  # bought then sold same qty at same price
    assert snap["positions"] == []  # position closed out


async def test_avg_cost_blends_across_two_buys(db_session):
    await _seed_symbol(db_session, close=100.0)
    acct = await paper_trading.open_account(db_session, "blender", 100_000.0)
    await paper_trading.place_order(db_session, acct.id, "AAPL", "buy", 10)  # @100
    # bump the market price, then buy again
    from datetime import date as _date

    db_session.add(
        Price(ticker_symbol="AAPL", trade_date=_date(2026, 1, 6), open=200, high=200, low=200, close=200.0, volume=1.0)
    )
    await db_session.commit()
    await paper_trading.place_order(db_session, acct.id, "AAPL", "buy", 10)  # @200

    snap = await paper_trading.account_snapshot(db_session, acct.id)
    pos = snap["positions"][0]
    assert pos["quantity"] == 20
    assert pos["avg_cost"] == 150.0  # (10*100 + 10*200)/20
    assert pos["unrealized_pnl"] == 1000.0  # (200-150)*20


async def test_limit_order_not_marketable_rejected(db_session):
    await _seed_symbol(db_session, close=100.0)
    acct = await paper_trading.open_account(db_session, "limiter", 10_000.0)
    # willing to pay at most 90 while market is 100 -> not marketable
    order = await paper_trading.place_order(
        db_session, acct.id, "AAPL", "buy", 5, order_type="limit", limit_price=90.0
    )
    assert order.status == "rejected"
    assert "not marketable" in order.reason


async def test_unknown_symbol_and_bad_input_raise(db_session):
    acct = await paper_trading.open_account(db_session, "errs", 10_000.0)
    with pytest.raises(OrderError):
        await paper_trading.place_order(db_session, acct.id, "ZZZZ", "buy", 1)
    with pytest.raises(OrderError):
        await paper_trading.place_order(db_session, acct.id, "AAPL", "buy", 0)
