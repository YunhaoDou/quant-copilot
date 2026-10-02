"""Fund analysis: live premium/discount snapshot (on-exchange ETF/LOF only) + quant
metrics computed from stored NAV/price history (any fund type).

Premium/discount needs a same-moment (price, IOPV) pair, so it's read live from AKShare's
realtime spot table rather than reconstructed from daily history — a same-day price/NAV
merge would need T+1 alignment handling for QDII funds, which this MVP skips.
"""
from dataclasses import dataclass

import akshare as ak
import numpy as np
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import fund_data

TRADING_DAYS_PER_YEAR = 252

WARNING_HIGH = 1.5
DANGER_HIGH = 3.0
WARNING_LOW = -1.5
DANGER_LOW = -3.0

LEVEL_NORMAL = "normal"
LEVEL_WARNING = "warning"
LEVEL_DANGER = "danger"


@dataclass
class PremiumSnapshot:
    code: str
    name: str
    price: float
    iopv: float
    premium_rate: float
    alert_level: str
    alert_message: str


def _assess_alert(premium_rate: float) -> tuple[str, str]:
    if premium_rate >= DANGER_HIGH:
        return LEVEL_DANGER, f"High premium {premium_rate:+.2f}% — above danger line {DANGER_HIGH}%"
    if premium_rate >= WARNING_HIGH:
        return LEVEL_WARNING, f"Elevated premium {premium_rate:+.2f}% — near warning line {WARNING_HIGH}%"
    if premium_rate <= DANGER_LOW:
        return LEVEL_DANGER, f"Deep discount {premium_rate:+.2f}% — below danger line {DANGER_LOW}%"
    if premium_rate <= WARNING_LOW:
        return LEVEL_WARNING, f"Wide discount {premium_rate:+.2f}% — near warning line {WARNING_LOW}%"
    return LEVEL_NORMAL, f"Premium/discount normal ({premium_rate:+.2f}%)"


def get_premium_snapshot(code: str, fund_type: str) -> PremiumSnapshot | None:
    """Live premium/discount for an ETF/LOF. Returns None if IOPV isn't published for it."""
    spot_fn = ak.fund_lof_spot_em if fund_type == "LOF" else ak.fund_etf_spot_em
    df = fund_data._retry(spot_fn)
    row = df[df["代码"] == code]
    if row.empty:
        return None
    r = row.iloc[0]
    iopv = r.get("IOPV实时估值")
    if iopv is None or pd.isna(iopv):
        return None
    price = float(r["最新价"])
    iopv = float(iopv)
    premium_rate = round((price - iopv) / iopv * 100, 4) if iopv else 0.0
    level, message = _assess_alert(premium_rate)
    return PremiumSnapshot(
        code=code,
        name=str(r["名称"]),
        price=price,
        iopv=iopv,
        premium_rate=premium_rate,
        alert_level=level,
        alert_message=message,
    )


def compute_metrics(nav_series: pd.Series) -> dict:
    """Total/annualized return, volatility, Sharpe, max drawdown, win rate from a
    date-indexed nav/close series. Risk-free rate fixed at 2%/yr (MVP simplification)."""
    if len(nav_series) < 2:
        return {
            "total_return": 0.0, "annualized_return": 0.0, "volatility": 0.0,
            "sharpe_ratio": 0.0, "max_drawdown": 0.0, "win_rate": 0.0, "window_days": len(nav_series),
        }

    daily_returns = nav_series.pct_change().dropna() * 100
    total_return = (nav_series.iloc[-1] / nav_series.iloc[0] - 1) * 100
    years = len(nav_series) / TRADING_DAYS_PER_YEAR
    annualized_return = ((nav_series.iloc[-1] / nav_series.iloc[0]) ** (1 / years) - 1) * 100 if years > 0 else 0.0
    volatility = float(daily_returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR))

    rf_daily = 2.0 / TRADING_DAYS_PER_YEAR
    excess = daily_returns - rf_daily
    sharpe = float(excess.mean() / excess.std() * np.sqrt(TRADING_DAYS_PER_YEAR)) if excess.std() else 0.0

    rolling_max = nav_series.cummax()
    max_drawdown = float(((nav_series - rolling_max) / rolling_max * 100).min())
    win_rate = float((daily_returns > 0).mean() * 100)

    return {
        "total_return": round(float(total_return), 2),
        "annualized_return": round(annualized_return, 2),
        "volatility": round(volatility, 2),
        "sharpe_ratio": round(sharpe, 4),
        "max_drawdown": round(max_drawdown, 2),
        "win_rate": round(win_rate, 2),
        "window_days": len(nav_series),
    }


async def get_fund_analysis(session: AsyncSession, code: str, fund_type: str) -> dict:
    """Combines stored NAV history metrics with a live premium/discount snapshot
    (ETF/LOF only — OTC funds have no on-exchange price to compare against IOPV)."""
    nav_series = await fund_data.load_nav_series(session, code)
    metrics = compute_metrics(nav_series)

    premium = None
    if fund_type in ("ETF", "LOF"):
        snapshot = get_premium_snapshot(code, fund_type)
        if snapshot:
            premium = {
                "price": snapshot.price,
                "iopv": snapshot.iopv,
                "premium_rate": snapshot.premium_rate,
                "alert_level": snapshot.alert_level,
                "alert_message": snapshot.alert_message,
            }

    return {"code": code, "fund_type": fund_type, "metrics": metrics, "premium": premium}
