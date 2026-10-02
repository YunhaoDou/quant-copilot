"""M5 risk panel: exposure, concentration, and drawdown metrics for a paper account.

All metrics are computed from data we already have — the account's positions plus the
ingested price history. The drawdown/volatility figures mark the account's *current*
holdings (fixed share counts) back over real historical prices, holding cash constant;
i.e. "if I had held exactly this book over the last N trading days, what would the
equity curve have looked like." That is a hypothetical, not a realized track record.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PaperPosition
from app.services.paper_trading import OrderError, _get_account, latest_price

# Alert thresholds (fractions of equity unless noted).
MAX_POSITION_WEIGHT = 0.40  # single position share of equity
MIN_CASH_PCT = 0.05  # cash buffer floor
MAX_DRAWDOWN_LIMIT = -0.20  # window drawdown floor
DRAWDOWN_WINDOW = 252  # ~1 trading year


@dataclass
class _Holding:
    symbol: str
    quantity: int
    market_value: float


async def _load_close(session: AsyncSession, symbol: str) -> pd.Series:
    from app.models import Price

    rows = (
        await session.execute(
            select(Price.trade_date, Price.close)
            .where(Price.ticker_symbol == symbol)
            .order_by(Price.trade_date)
        )
    ).all()
    if not rows:
        return pd.Series(dtype=float)
    return pd.Series([r.close for r in rows], index=pd.DatetimeIndex([r.trade_date for r in rows]))


def _portfolio_drawdown(
    cash: float, shares: dict[str, int], closes: dict[str, pd.Series], window: int
) -> dict:
    """Mark current holdings over aligned historical closes -> drawdown + annualized vol."""
    series = {s: c for s, c in closes.items() if not c.empty and shares.get(s)}
    if not series:
        return {"max_drawdown": 0.0, "annualized_vol": 0.0, "window_days": 0}

    prices = pd.DataFrame(series).dropna()  # inner-join on common trading dates
    if len(prices) < 2:
        return {"max_drawdown": 0.0, "annualized_vol": 0.0, "window_days": len(prices)}

    prices = prices.tail(window)
    equity = cash + prices.mul(pd.Series(shares)).sum(axis=1)
    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    daily_ret = equity.pct_change().dropna()
    vol = float(daily_ret.std() * np.sqrt(252)) if len(daily_ret) > 1 else 0.0
    return {
        "max_drawdown": round(float(drawdown.min()), 4),
        "annualized_vol": round(vol, 4),
        "window_days": int(len(prices)),
    }


async def risk_snapshot(session: AsyncSession, account_id: int) -> dict:
    account = await _get_account(session, account_id)
    positions = (
        await session.execute(select(PaperPosition).where(PaperPosition.account_id == account_id))
    ).scalars().all()

    holdings: list[_Holding] = []
    shares: dict[str, int] = {}
    closes: dict[str, pd.Series] = {}
    positions_value = 0.0
    for pos in positions:
        px = await latest_price(session, pos.ticker_symbol)
        px = px if px is not None else pos.avg_cost
        mv = pos.quantity * px
        positions_value += mv
        holdings.append(_Holding(pos.ticker_symbol, pos.quantity, mv))
        shares[pos.ticker_symbol] = pos.quantity
        closes[pos.ticker_symbol] = await _load_close(session, pos.ticker_symbol)

    equity = account.cash_balance + positions_value
    cash_pct = account.cash_balance / equity if equity else 1.0

    # Concentration: weights within the holdings book (sum to 1), plus HHI.
    exposures = []
    hhi = 0.0
    for h in holdings:
        w_book = h.market_value / positions_value if positions_value else 0.0
        w_equity = h.market_value / equity if equity else 0.0
        hhi += w_book**2
        exposures.append(
            {
                "symbol": h.symbol,
                "market_value": round(h.market_value, 2),
                "weight_of_book": round(w_book, 4),
                "weight_of_equity": round(w_equity, 4),
            }
        )
    exposures.sort(key=lambda e: e["market_value"], reverse=True)
    effective_positions = round(1.0 / hhi, 2) if hhi else 0.0
    top3_weight = round(sum(e["weight_of_book"] for e in exposures[:3]), 4)
    largest = exposures[0] if exposures else None

    dd = _portfolio_drawdown(account.cash_balance, shares, closes, DRAWDOWN_WINDOW)

    # Alerts
    alerts: list[dict] = []
    if largest and largest["weight_of_equity"] > MAX_POSITION_WEIGHT:
        alerts.append(
            {
                "level": "warning",
                "code": "concentration",
                "message": f"{largest['symbol']} is {largest['weight_of_equity'] * 100:.0f}% of equity "
                f"(> {MAX_POSITION_WEIGHT * 100:.0f}% limit)",
            }
        )
    if len(holdings) > 1 and effective_positions < 2:
        alerts.append(
            {
                "level": "warning",
                "code": "diversification",
                "message": f"effective positions {effective_positions} < 2 — book is concentrated",
            }
        )
    if equity and cash_pct < MIN_CASH_PCT:
        alerts.append(
            {
                "level": "warning",
                "code": "low_cash",
                "message": f"cash buffer {cash_pct * 100:.1f}% (< {MIN_CASH_PCT * 100:.0f}% floor)",
            }
        )
    if dd["max_drawdown"] < MAX_DRAWDOWN_LIMIT:
        alerts.append(
            {
                "level": "warning",
                "code": "drawdown",
                "message": f"{dd['window_days']}-day portfolio drawdown {dd['max_drawdown'] * 100:.0f}% "
                f"(< {MAX_DRAWDOWN_LIMIT * 100:.0f}% limit)",
            }
        )

    return {
        "account_id": account.id,
        "name": account.name,
        "equity": round(equity, 2),
        "gross_exposure": round(positions_value, 2),
        "net_exposure": round(positions_value, 2),  # long-only book: gross == net
        "cash": round(account.cash_balance, 2),
        "cash_pct": round(cash_pct, 4),
        "leverage": round(positions_value / equity, 4) if equity else 0.0,
        "num_positions": len(holdings),
        "hhi": round(hhi, 4),
        "effective_positions": effective_positions,
        "largest_position_weight": largest["weight_of_equity"] if largest else 0.0,
        "top3_weight_of_book": top3_weight,
        "drawdown": dd,
        "exposures": exposures,
        "alerts": alerts,
        "thresholds": {
            "max_position_weight": MAX_POSITION_WEIGHT,
            "min_cash_pct": MIN_CASH_PCT,
            "max_drawdown": MAX_DRAWDOWN_LIMIT,
        },
    }


# Re-export so route can catch the same error type as paper trading.
__all__ = ["risk_snapshot", "OrderError"]
