"""Fund analysis: live premium/discount snapshot (on-exchange ETF/LOF only) + quant
metrics computed from stored NAV/price history (any fund type).

Premium/discount needs a same-moment (price, IOPV) pair, so it's read live from AKShare's
realtime spot table rather than reconstructed from daily history — a same-day price/NAV
merge would need T+1 alignment handling for QDII funds, which this MVP skips.
"""
from dataclasses import dataclass
import asyncio
from time import monotonic

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
    provider: str = "东方财富"
    source_url: str | None = None
    fetched_at: str | None = None
    source_attempts: list | None = None


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


class PremiumSourceError(RuntimeError):
    """可解释的源端失败；不将失败转换为零溢价。"""
    def __init__(self,category,attempts):
        self.category=category;self.attempts=attempts
        super().__init__("IOPV公开源暂不可用，请稍后重试")


PREMIUM_NODES=("https://push2.eastmoney.com","https://82.push2.eastmoney.com")


def get_premium_snapshot(code: str, fund_type: str) -> PremiumSnapshot | None:
    """同一响应配对价格与IOPV；最多两个同供应商节点，不拼接跨源数据。"""
    from app.cycle.market import normalize_symbol
    from app.cycle.live import number,TZ
    from datetime import datetime
    symbol=normalize_symbol(code)
    code=symbol[2:]
    secid=("1." if symbol.startswith("sh") else "0.")+code
    attempts=[];started=monotonic()
    with httpx.Client(trust_env=False,timeout=httpx.Timeout(2,connect=1)) as client:
        for node in PREMIUM_NODES:
            if monotonic()-started>=6:break
            url=node+"/api/qt/ulist.np/get"
            try:
                response=client.get(url,params={"secids":secid,"fltt":2,"fields":"f12,f14,f2,f441,f124"})
                response.raise_for_status();body=response.json()
                if not isinstance(body,dict) or not isinstance(body.get("data"),dict):raise ValueError("invalid_response")
                rows=body["data"].get("diff")
                if not isinstance(rows,list):raise ValueError("invalid_response")
                if not rows:return None
                row=next((r for r in rows if isinstance(r,dict) and str(r.get("f12"))==code),None)
                if row is None:raise ValueError("code_mismatch")
                iopv,price=number(row.get("f441")),number(row.get("f2"))
                if iopv is None or iopv<=0:return None
                if price is None or price<=0:raise ValueError("invalid_price")
                stamp=row.get("f124")
                quote_time=datetime.fromtimestamp(float(stamp),TZ).isoformat() if stamp else None
                rate=round((price-iopv)/iopv*100,4);level,message=_assess_alert(rate)
                attempts.append({"url":url,"status":"ok"})
                return PremiumSnapshot(code=code,name=str(row.get("f14") or code),price=price,iopv=iopv,
                    premium_rate=rate,alert_level=level,alert_message=message,quote_time=quote_time,
                    source_url=url,fetched_at=datetime.now(TZ).isoformat(),source_attempts=attempts)
            except httpx.TimeoutException:category="timeout"
            except httpx.HTTPStatusError as exc:
                category="rate_limited" if exc.response.status_code==429 else "http_error"
                attempts.append({"url":url,"status":category,"http_status":exc.response.status_code})
                if category=="rate_limited":break
                continue
            except httpx.DecodingError:category="invalid_response"
            except httpx.RequestError:category="connection_error"
            except (ValueError,TypeError,OverflowError) as exc:
                category=str(exc) if str(exc) in ("code_mismatch","invalid_price") else "invalid_response"
            attempts.append({"url":url,"status":category})
    raise PremiumSourceError(attempts[-1]["status"] if attempts else "timeout",attempts)


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
    premium_status={"state":"not_applicable","message":"该基金类型不适用场内IOPV折溢价"}
    if fund_type in ("ETF", "LOF"):
        try:
            snapshot=await asyncio.wait_for(asyncio.to_thread(get_premium_snapshot,code,fund_type),timeout=7)
            premium_status={"state":"available" if snapshot else "missing","message":"已读取同一响应的价格与IOPV" if snapshot else "供应商未提供有效IOPV，保留未知，不以历史净值替代"}
        except PremiumSourceError as exc:
            snapshot=None;premium_status={"state":"unavailable","category":exc.category,"attempts":exc.attempts,"message":str(exc)}
        except asyncio.TimeoutError:
            snapshot=None;premium_status={"state":"unavailable","category":"timeout","message":"IOPV读取超时，已保留净值指标；可稍后重试"}
        if snapshot:
            premium = {
                "price": snapshot.price,
                "iopv": snapshot.iopv,
                "premium_rate": snapshot.premium_rate,
                "alert_level": snapshot.alert_level,
                "alert_message": snapshot.alert_message,
                "quote_time": snapshot.quote_time,
                "provider":snapshot.provider,"source_url":snapshot.source_url,
                "fetched_at":snapshot.fetched_at,"source_attempts":snapshot.source_attempts,
            }

    return {"code": code, "fund_type": fund_type, "metrics": metrics, "premium": premium,"premium_status":premium_status}
