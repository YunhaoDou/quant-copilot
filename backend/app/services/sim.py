"""Month-long systematic paper-trading simulation.

Four strategy templates run in parallel, each in its own paper account, plus a SPY
buy-and-hold benchmark account. Every trading day we:
  1. compute each strategy's *current target position* (long/flat) per symbol, using only
     price history available up to that day (walk-forward, no look-ahead);
  2. reconcile the account's holdings to that target (buy a fixed dollar slice on a
     flat->long flip, sell the whole position on a long->flat flip);
  3. log each account's equity so a net-value curve can be plotted vs SPY at month end.

Execution model note: signals are derived from daily closes and fills use the latest
close (see paper_trading). Running the job once per real trading day makes the test
genuinely out-of-sample; the same-bar signal/fill is an accepted ~1-bar simplification,
documented in docs/sim-protocol.md.
"""
from datetime import date

import numpy as np
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PaperAccount, PaperPosition, SimEquity
from app.services import paper_trading
from app.services.strategies import STRATEGIES

SIM_STRATEGIES = list(STRATEGIES.keys())  # all four templates
SIM_UNIVERSE = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA"]
BENCHMARK_SYMBOL = "SPY"
BENCHMARK_ACCOUNT = "sim-benchmark-spy"


def account_name(strategy_key: str) -> str:
    return f"sim-{strategy_key}"


def current_target_long(close, strategy_key: str) -> bool:
    """Return True if the strategy's current state is 'in the market' as of the last bar.

    Walks the strategy's entry/exit events into a position state machine and returns the
    final state. Uses only the bars present in `close`, so calling it each day with the
    history-up-to-that-day is look-ahead-free.
    """
    if strategy_key not in STRATEGIES:
        raise ValueError(f"unknown strategy: {strategy_key}")
    if close is None or len(close) < 2:
        return False
    entries, exits = STRATEGIES[strategy_key]["fn"](close)
    e = np.asarray(entries).astype(bool).ravel()
    x = np.asarray(exits).astype(bool).ravel()
    state = False
    for i in range(len(e)):
        if not state and e[i]:
            state = True
        elif state and x[i]:
            state = False
    return bool(state)


async def _position_qty(session: AsyncSession, account_id: int, symbol: str) -> int:
    pos = (
        await session.execute(
            select(PaperPosition).where(
                PaperPosition.account_id == account_id, PaperPosition.ticker_symbol == symbol
            )
        )
    ).scalar_one_or_none()
    return pos.quantity if pos else 0


async def _log_equity(session: AsyncSession, account_id: int, on_date: date) -> dict:
    snap = await paper_trading.account_snapshot(session, account_id)
    stmt = insert(SimEquity).values(
        account_id=account_id,
        trade_date=on_date,
        equity=snap["total_equity"],
        cash=snap["cash_balance"],
        positions_value=snap["positions_value"],
        num_positions=len(snap["positions"]),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["account_id", "trade_date"],
        set_={
            "equity": stmt.excluded.equity,
            "cash": stmt.excluded.cash,
            "positions_value": stmt.excluded.positions_value,
            "num_positions": stmt.excluded.num_positions,
        },
    )
    await session.execute(stmt)
    await session.commit()
    return snap


async def init_sim(session: AsyncSession, starting_cash: float = 1000.0) -> dict:
    """Create the strategy accounts + SPY benchmark. Idempotent: skips ones that exist."""
    created = []
    for key in SIM_STRATEGIES:
        name = account_name(key)
        if (await session.execute(select(PaperAccount).where(PaperAccount.name == name))).scalar_one_or_none():
            continue
        await paper_trading.open_account(session, name, starting_cash)
        created.append(name)

    bench = (
        await session.execute(select(PaperAccount).where(PaperAccount.name == BENCHMARK_ACCOUNT))
    ).scalar_one_or_none()
    if bench is None:
        bench = await paper_trading.open_account(session, BENCHMARK_ACCOUNT, starting_cash)
        price = await paper_trading.latest_price(session, BENCHMARK_SYMBOL)
        if price:
            shares = int(starting_cash // price)
            if shares > 0:
                await paper_trading.place_order(session, bench.id, BENCHMARK_SYMBOL, "buy", shares)
        created.append(BENCHMARK_ACCOUNT)

    return {"created": created, "starting_cash": starting_cash}


async def run_sim_day(session: AsyncSession, on_date: date | None = None) -> dict:
    """One walk-forward step: reconcile every strategy account to its current signal,
    then log equity for all sim accounts (strategies + benchmark)."""
    on_date = on_date or date.today()
    actions: list[dict] = []

    for key in SIM_STRATEGIES:
        name = account_name(key)
        acct = (
            await session.execute(select(PaperAccount).where(PaperAccount.name == name))
        ).scalar_one_or_none()
        if acct is None:
            continue
        budget = acct.starting_cash / len(SIM_UNIVERSE)  # equal-weight dollar slice per symbol
        for symbol in SIM_UNIVERSE:
            close = await _load_close(session, symbol)
            target_long = current_target_long(close, key)
            held = await _position_qty(session, acct.id, symbol)
            price = await paper_trading.latest_price(session, symbol)
            if price is None:
                continue
            if target_long and held == 0:
                shares = int(budget // price)
                if shares > 0:
                    order = await paper_trading.place_order(session, acct.id, symbol, "buy", shares)
                    actions.append({"account": name, "symbol": symbol, "action": "buy", "status": order.status})
            elif not target_long and held > 0:
                order = await paper_trading.place_order(session, acct.id, symbol, "sell", held)
                actions.append({"account": name, "symbol": symbol, "action": "sell", "status": order.status})

    # Log equity for every sim account, including the benchmark.
    equities = {}
    accounts = (
        await session.execute(
            select(PaperAccount).where(PaperAccount.name.like("sim-%"))
        )
    ).scalars().all()
    for acct in accounts:
        snap = await _log_equity(session, acct.id, on_date)
        equities[acct.name] = snap["total_equity"]

    return {"date": on_date.isoformat(), "actions": actions, "equities": equities}


async def _load_close(session: AsyncSession, symbol: str):
    from app.models import Price

    rows = (
        await session.execute(
            select(Price.trade_date, Price.close)
            .where(Price.ticker_symbol == symbol)
            .order_by(Price.trade_date)
        )
    ).all()
    if not rows:
        return None
    import pandas as pd

    return pd.Series([r.close for r in rows], index=pd.DatetimeIndex([r.trade_date for r in rows]))


async def sim_report(session: AsyncSession) -> dict:
    """Latest equity + total return per sim account, ranked, with SPY delta."""
    accounts = (
        await session.execute(select(PaperAccount).where(PaperAccount.name.like("sim-%")).order_by(PaperAccount.name))
    ).scalars().all()

    rows = []
    bench_return = None
    for acct in accounts:
        curve = (
            await session.execute(
                select(SimEquity.trade_date, SimEquity.equity)
                .where(SimEquity.account_id == acct.id)
                .order_by(SimEquity.trade_date)
            )
        ).all()
        latest_equity = curve[-1].equity if curve else acct.cash_balance
        total_return = (latest_equity / acct.starting_cash - 1) * 100 if acct.starting_cash else 0.0
        row = {
            "account": acct.name,
            "days_logged": len(curve),
            "starting_cash": round(acct.starting_cash, 2),
            "equity": round(latest_equity, 2),
            "total_return_pct": round(total_return, 2),
        }
        if acct.name == BENCHMARK_ACCOUNT:
            bench_return = total_return
        rows.append(row)

    for row in rows:
        row["vs_spy_pct"] = (
            round(row["total_return_pct"] - bench_return, 2) if bench_return is not None else None
        )

    strategies = sorted(
        [r for r in rows if r["account"] != BENCHMARK_ACCOUNT],
        key=lambda r: r["total_return_pct"],
        reverse=True,
    )
    benchmark = next((r for r in rows if r["account"] == BENCHMARK_ACCOUNT), None)
    return {"benchmark": benchmark, "strategies": strategies}
