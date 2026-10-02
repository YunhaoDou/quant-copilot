"""M4 paper-trading engine: accounts, order execution, and account snapshots.

Execution model (research sandbox, not a live venue):
- The "market price" of a symbol is its latest ingested close (from the `prices` table).
- Market orders fill at that price unconditionally (subject to cash / position checks).
- Limit orders fill at the latest close only if marketable: buy needs limit >= close,
  sell needs limit <= close; otherwise the order is rejected (no resting book).
- Stop orders trigger when the latest close crosses the stop: buy-stop needs close >= stop,
  sell-stop needs close <= stop; they then fill at the latest close.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PaperAccount, PaperOrder, PaperPosition, Price, Ticker
from app.services import notifications


class OrderError(ValueError):
    """Raised when an order is invalid (bad input, unknown symbol, no price data)."""


async def latest_price(session: AsyncSession, symbol: str) -> float | None:
    """Most recent ingested close for a symbol, or None if no price data."""
    result = await session.execute(
        select(Price.close)
        .where(Price.ticker_symbol == symbol)
        .order_by(Price.trade_date.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def open_account(session: AsyncSession, name: str, starting_cash: float) -> PaperAccount:
    if starting_cash <= 0:
        raise OrderError("starting_cash must be positive")
    exists = await session.execute(select(PaperAccount).where(PaperAccount.name == name))
    if exists.scalar_one_or_none() is not None:
        raise OrderError(f"account '{name}' already exists")
    account = PaperAccount(name=name, starting_cash=starting_cash, cash_balance=starting_cash)
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return account


async def _get_account(session: AsyncSession, account_id: int) -> PaperAccount:
    account = (
        await session.execute(select(PaperAccount).where(PaperAccount.id == account_id))
    ).scalar_one_or_none()
    if account is None:
        raise OrderError(f"account {account_id} not found")
    return account


async def _get_position(session: AsyncSession, account_id: int, symbol: str) -> PaperPosition | None:
    return (
        await session.execute(
            select(PaperPosition).where(
                PaperPosition.account_id == account_id, PaperPosition.ticker_symbol == symbol
            )
        )
    ).scalar_one_or_none()


def _is_marketable(side: str, order_type: str, limit_price: float | None, price: float) -> tuple[bool, str]:
    """Return (marketable, reason). reason is set only when not marketable."""
    if order_type == "market":
        return True, ""
    if limit_price is None:
        return False, f"{order_type} order requires limit_price"
    if order_type == "limit":
        if side == "buy" and limit_price >= price:
            return True, ""
        if side == "sell" and limit_price <= price:
            return True, ""
        return False, f"limit {limit_price} not marketable vs close {price:.2f}"
    if order_type == "stop":
        if side == "buy" and price >= limit_price:
            return True, ""
        if side == "sell" and price <= limit_price:
            return True, ""
        return False, f"stop {limit_price} not triggered vs close {price:.2f}"
    return False, f"unknown order_type '{order_type}'"


async def place_order(
    session: AsyncSession,
    account_id: int,
    symbol: str,
    side: str,
    quantity: int,
    order_type: str = "market",
    limit_price: float | None = None,
) -> PaperOrder:
    """Validate, execute against the latest close, mutate cash/position, and record the order."""
    symbol = symbol.upper()
    side = side.lower()
    order_type = order_type.lower()
    if side not in ("buy", "sell"):
        raise OrderError("side must be 'buy' or 'sell'")
    if order_type not in ("market", "limit", "stop"):
        raise OrderError("order_type must be 'market', 'limit', or 'stop'")
    if quantity <= 0:
        raise OrderError("quantity must be a positive integer")

    account = await _get_account(session, account_id)
    if (await session.execute(select(Ticker).where(Ticker.symbol == symbol))).scalar_one_or_none() is None:
        raise OrderError(f"unknown ticker '{symbol}'")
    price = await latest_price(session, symbol)
    if price is None:
        raise OrderError(f"no price data for '{symbol}' — ingest it first")

    order = PaperOrder(
        account_id=account_id,
        ticker_symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        limit_price=limit_price,
    )

    def reject(reason: str) -> PaperOrder:
        order.status = "rejected"
        order.reason = reason
        session.add(order)
        return order

    marketable, reason = _is_marketable(side, order_type, limit_price, price)
    if not marketable:
        rejected = reject(reason)
        await session.commit()
        await session.refresh(rejected)
        return rejected

    position = await _get_position(session, account_id, symbol)

    if side == "buy":
        cost = quantity * price
        if cost > account.cash_balance:
            rejected = reject(f"insufficient cash: need {cost:.2f}, have {account.cash_balance:.2f}")
            await session.commit()
            await session.refresh(rejected)
            return rejected
        account.cash_balance -= cost
        if position is None:
            position = PaperPosition(
                account_id=account_id, ticker_symbol=symbol, quantity=quantity, avg_cost=price
            )
            session.add(position)
        else:
            total_qty = position.quantity + quantity
            position.avg_cost = (position.quantity * position.avg_cost + quantity * price) / total_qty
            position.quantity = total_qty
    else:  # sell
        if position is None or position.quantity < quantity:
            held = position.quantity if position else 0
            rejected = reject(f"insufficient shares: need {quantity}, hold {held}")
            await session.commit()
            await session.refresh(rejected)
            return rejected
        account.cash_balance += quantity * price
        position.quantity -= quantity
        if position.quantity == 0:
            await session.delete(position)

    order.status = "filled"
    order.fill_price = price
    session.add(order)
    await session.commit()
    await session.refresh(order)

    await notifications.notify_all(
        f"Paper trade filled: {side.upper()} {quantity} {symbol} @ {price:.2f} (account {account_id})"
    )
    return order


async def account_snapshot(session: AsyncSession, account_id: int) -> dict:
    """Cash, per-position market value and unrealized P&L, and total equity."""
    account = await _get_account(session, account_id)
    positions = (
        await session.execute(select(PaperPosition).where(PaperPosition.account_id == account_id))
    ).scalars().all()

    holdings = []
    positions_value = 0.0
    for pos in positions:
        mkt = await latest_price(session, pos.ticker_symbol)
        mkt = mkt if mkt is not None else pos.avg_cost
        market_value = pos.quantity * mkt
        cost_basis = pos.quantity * pos.avg_cost
        positions_value += market_value
        holdings.append(
            {
                "symbol": pos.ticker_symbol,
                "quantity": pos.quantity,
                "avg_cost": round(pos.avg_cost, 4),
                "last_price": round(mkt, 4),
                "market_value": round(market_value, 2),
                "unrealized_pnl": round(market_value - cost_basis, 2),
                "unrealized_pnl_pct": round((mkt / pos.avg_cost - 1) * 100, 2) if pos.avg_cost else 0.0,
            }
        )

    total_equity = account.cash_balance + positions_value
    return {
        "account_id": account.id,
        "name": account.name,
        "cash_balance": round(account.cash_balance, 2),
        "positions_value": round(positions_value, 2),
        "total_equity": round(total_equity, 2),
        "starting_cash": round(account.starting_cash, 2),
        "total_return_pct": round((total_equity / account.starting_cash - 1) * 100, 2),
        "positions": holdings,
    }


async def list_orders(session: AsyncSession, account_id: int) -> list[PaperOrder]:
    await _get_account(session, account_id)
    result = await session.execute(
        select(PaperOrder).where(PaperOrder.account_id == account_id).order_by(PaperOrder.id.desc())
    )
    return list(result.scalars().all())
