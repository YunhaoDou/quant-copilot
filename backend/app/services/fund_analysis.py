"""Fund analysis: live premium/discount snapshot (on-exchange ETF/LOF only) + quant
metrics computed from stored NAV/price history (any fund type).

Premium/discount needs a same-moment (price, IOPV) pair, so it's read live from AKShare's
realtime spot table rather than reconstructed from daily history — a same-day price/NAV
merge would need T+1 alignment handling for QDII funds, which this MVP skips.
"""
from dataclasses import dataclass

import pandas as pd
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import fund_data, indicators

TRADING_DAYS_PER_YEAR = 252
RISK_FREE_RATE = 0.02  # annualized, MVP simplification (2%/yr)

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
    quote_time: str | None = None


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
    from app.cycle.market import normalize_symbol
    from app.cycle.live import number, TZ
    from datetime import datetime
    symbol = normalize_symbol(code)
    secid = ("1." if symbol.startswith("sh") else "0.")+code
    with httpx.Client(trust_env=False, timeout=8) as client:
        response = client.get("https://push2.eastmoney.com/api/qt/ulist.np/get", params={"secids":secid, "fltt":2, "fields":"f12,f14,f2,f441,f124"})
        response.raise_for_status()
        rows = (response.json().get("data") or {}).get("diff", [])
    if not rows:
        return None
    r = rows[0]
    iopv, price = number(r.get("f441")), number(r.get("f2"))
    if iopv is None or iopv <= 0 or price is None:
        return None
    premium_rate = round((price - iopv) / iopv * 100, 4) if iopv else 0.0
    level, message = _assess_alert(premium_rate)
    return PremiumSnapshot(
        code=code,
        name=str(r["f14"]),
        price=price,
        iopv=iopv,
        premium_rate=premium_rate,
        alert_level=level,
        alert_message=message,
        quote_time=datetime.fromtimestamp(r["f124"], TZ).isoformat() if r.get("f124") else None,
    )


def compute_metrics(nav_series: pd.Series) -> dict:
    """Total/annualized return, volatility, Sharpe, max drawdown, win rate from a
    date-indexed nav/close series. Risk-free rate fixed at 2%/yr (MVP simplification).

    Conventions preserved from this panel: annualization counts the first observation as
    a period (``periods=len(nav_series)``), the Sharpe denominator is the annualized
    volatility of the return series, and every figure is percent/2dp (Sharpe 4dp)."""
    if len(nav_series) < 2:
        return {
            "total_return": 0.0, "annualized_return": 0.0, "volatility": 0.0,
            "sharpe_ratio": 0.0, "max_drawdown": 0.0, "win_rate": 0.0, "window_days": len(nav_series),
        }

    daily_returns = nav_series.pct_change().dropna()
    total_return = indicators.total_return(nav_series) * 100
    annualized_return = indicators.annualized_return(
        nav_series, periods_per_year=TRADING_DAYS_PER_YEAR, periods=len(nav_series)
    ) * 100
    volatility = indicators.annualized_volatility(daily_returns, TRADING_DAYS_PER_YEAR) * 100

    sharpe = indicators.sharpe(daily_returns, risk_free=RISK_FREE_RATE, periods_per_year=TRADING_DAYS_PER_YEAR)
    # The old implementation returned 0.0 (not NaN) when the return series had no spread;
    # indicators.sharpe returns None exactly for that zero-volatility case.
    sharpe_ratio = 0.0 if sharpe is None else sharpe

    max_drawdown = indicators.max_drawdown(nav_series) * 100
    win_rate = indicators.win_rate(daily_returns) * 100

    return {
        "total_return": round(float(total_return), 2),
        "annualized_return": round(annualized_return, 2),
        "volatility": round(volatility, 2),
        "sharpe_ratio": round(float(sharpe_ratio), 4),
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
                "quote_time": snapshot.quote_time,
            }

    return {"code": code, "fund_type": fund_type, "metrics": metrics, "premium": premium}
