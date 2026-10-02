"""Multi-factor cross-sectional stock screening: scores every ticker in the ingested
universe (minus benchmark ETFs) on 9 factors computed purely from stored OHLCV — including
the fund-flow Agent's own score, so its output literally feeds this one, matching the
"one agent's output is the next agent's input" contract from the original design note.
No new data source: same Price table everything else already reads.

Composite score = average of per-factor cross-sectional z-scores (equal-weighted, signed
so that "higher is always better"). Missing factors (not enough history yet) are simply
left out of a ticker's average rather than crashing the whole screen.
"""
from dataclasses import dataclass, field
from statistics import mean, pstdev

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import StockScore, Ticker
from app.services import fund_flow
from app.services.data_ingestion import load_ohlcv

BENCHMARK_SYMBOLS = {"SPY", "510300.SS"}  # benchmark ETFs, not individual stock picks

FACTOR_DIRECTION = {
    "momentum_3m": 1,
    "momentum_12m": 1,
    "volatility_20d": -1,  # lower realized vol is better
    "rsi_14": 1,
    "volume_trend": 1,
    "trend_vs_200ma": 1,
    "fund_flow_score": 1,
    "max_drawdown_1y": 1,  # stored as a negative number; closer to 0 (less negative) is better
    "sharpe_like": 1,
}

FACTOR_LABELS = {
    "en": {
        "momentum_3m": "3-month momentum",
        "momentum_12m": "12-month momentum",
        "volatility_20d": "low realized volatility",
        "rsi_14": "RSI momentum strength",
        "volume_trend": "rising trading interest",
        "trend_vs_200ma": "uptrend vs 200-day average",
        "fund_flow_score": "fund-flow inflow",
        "max_drawdown_1y": "shallow drawdown",
        "sharpe_like": "risk-adjusted return",
    },
    "zh": {
        "momentum_3m": "3个月动量",
        "momentum_12m": "12个月动量",
        "volatility_20d": "低已实现波动率",
        "rsi_14": "RSI动量强度",
        "volume_trend": "成交量趋势上升",
        "trend_vs_200ma": "站上200日均线",
        "fund_flow_score": "资金净流入",
        "max_drawdown_1y": "回撤较浅",
        "sharpe_like": "风险调整后收益",
    },
}
DEFAULT_LANG = "en"


@dataclass
class StockFactors:
    symbol: str
    as_of_date: pd.Timestamp
    values: dict = field(default_factory=dict)  # factor_name -> float | None


def _return_over(close: pd.Series, lookback: int, skip: int = 0) -> float | None:
    end_idx = len(close) - 1 - skip
    start_idx = end_idx - lookback
    if start_idx < 0:
        return None
    return float(close.iloc[end_idx] / close.iloc[start_idx] - 1)


def _volatility_20d(close: pd.Series) -> float | None:
    if len(close) < 21:
        return None
    daily_ret = close.pct_change().dropna().tail(20)
    return float(daily_ret.std() * np.sqrt(252))


def _rsi_14(close: pd.Series) -> float | None:
    if len(close) < 15:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean().iloc[-1]
    avg_loss = loss.rolling(14).mean().iloc[-1]
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100 - 100 / (1 + rs))


def _volume_trend(volume: pd.Series) -> float | None:
    if len(volume) < 60:
        return None
    vol20 = volume.tail(20).mean()
    vol60 = volume.tail(60).mean()
    if vol60 == 0:
        return None
    return float(vol20 / vol60)


def _trend_vs_200ma(close: pd.Series) -> float | None:
    if len(close) < 200:
        return None
    ma200 = close.tail(200).mean()
    if ma200 == 0:
        return None
    return float((close.iloc[-1] - ma200) / ma200)


def _max_drawdown_1y(close: pd.Series) -> float | None:
    if len(close) < 2:
        return None
    tail = close.tail(252)
    running_max = tail.cummax()
    drawdown = tail / running_max - 1.0
    return float(drawdown.min())


def _sharpe_like(close: pd.Series) -> float | None:
    daily_ret = close.pct_change().dropna().tail(252)
    if len(daily_ret) < 20:
        return None
    std = daily_ret.std()
    if std == 0:
        return None
    return float(daily_ret.mean() / std * np.sqrt(252))


def compute_stock_factors(df: pd.DataFrame, symbol: str) -> StockFactors:
    """Pure function: OHLCV DataFrame -> raw (unstandardized) factor values."""
    if df.empty:
        raise ValueError(f"{symbol}: no price history")
    close = df["close"]

    values: dict = {
        "momentum_3m": _return_over(close, 63),
        "momentum_12m": _return_over(close, 252, skip=21),
        "volatility_20d": _volatility_20d(close),
        "rsi_14": _rsi_14(close),
        "volume_trend": _volume_trend(df["volume"]),
        "trend_vs_200ma": _trend_vs_200ma(close),
        "max_drawdown_1y": _max_drawdown_1y(close),
        "sharpe_like": _sharpe_like(close),
    }
    try:
        values["fund_flow_score"] = fund_flow.compute_fund_flow(df, symbol).score
    except ValueError:
        values["fund_flow_score"] = None

    return StockFactors(symbol=symbol, as_of_date=df.index[-1], values=values)


def _zscore_universe(factor_values: dict[str, list[float]]) -> dict[str, dict[int, float]]:
    """factor_name -> {position_in_list: zscore}, computed cross-sectionally. Universe
    with < 2 non-null observations for a factor gets zscore 0 for everyone (undefined spread)."""
    zscores: dict[str, dict[int, float]] = {}
    for factor, values in factor_values.items():
        present = {i: v for i, v in enumerate(values) if v is not None}
        if len(present) < 2:
            zscores[factor] = {i: 0.0 for i in present}
            continue
        vals = list(present.values())
        mu, sigma = mean(vals), pstdev(vals)
        if sigma == 0:
            zscores[factor] = {i: 0.0 for i in present}
            continue
        zscores[factor] = {i: (v - mu) / sigma for i, v in present.items()}
    return zscores


def rank_universe(factors_list: list[StockFactors], lang: str = DEFAULT_LANG) -> list[dict]:
    """Cross-sectional z-score + equal-weighted composite + rank. Pure function so it's
    testable without a DB: pass in a list of StockFactors, get back a ranked list."""
    labels = FACTOR_LABELS.get(lang, FACTOR_LABELS[DEFAULT_LANG])
    factor_names = list(FACTOR_DIRECTION)
    per_factor_values = {f: [sf.values.get(f) for sf in factors_list] for f in factor_names}
    zscores = _zscore_universe(per_factor_values)

    results = []
    for i, sf in enumerate(factors_list):
        contributions = {}
        for factor in factor_names:
            z = zscores[factor].get(i)
            if z is None:
                continue
            contributions[factor] = FACTOR_DIRECTION[factor] * z
        composite = mean(contributions.values()) if contributions else 0.0
        top_reasons = sorted(contributions.items(), key=lambda kv: kv[1], reverse=True)[:2]
        reasons = [labels[f] for f, z in top_reasons if z > 0]

        results.append(
            {
                "symbol": sf.symbol,
                "as_of_date": sf.as_of_date,
                "composite_score": round(composite, 4),
                "factors": {k: (round(v, 4) if v is not None else None) for k, v in sf.values.items()},
                "reasons": reasons,
            }
        )

    results.sort(key=lambda r: r["composite_score"], reverse=True)
    for rank, r in enumerate(results, start=1):
        r["rank"] = rank
    return results


async def run_screening(
    session: AsyncSession,
    top_n: int = 10,
    lang: str = DEFAULT_LANG,
    market: str | None = None,
) -> dict:
    query = select(Ticker.symbol)
    if market is not None:
        query = query.where(Ticker.market == market)
    tickers = (await session.execute(query)).scalars().all()
    universe = [s for s in tickers if s not in BENCHMARK_SYMBOLS]

    factors_list = []
    for symbol in universe:
        df = await load_ohlcv(session, symbol)
        if df.empty:
            continue
        factors_list.append(compute_stock_factors(df, symbol))

    if not factors_list:
        return {"results": [], "universe_size": 0}

    ranked = rank_universe(factors_list, lang=lang)

    for r in ranked:
        existing = (
            await session.execute(
                select(StockScore).where(
                    StockScore.ticker_symbol == r["symbol"],
                    StockScore.as_of_date == r["as_of_date"].date(),
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = StockScore(ticker_symbol=r["symbol"], as_of_date=r["as_of_date"].date())
            session.add(existing)
        existing.composite_score = r["composite_score"]
        existing.rank = r["rank"]
        existing.factors = r["factors"]
        existing.reasons = r["reasons"]
        existing.method = "zscore_9factor_v1"
    await session.commit()

    return {
        "results": [
            {
                "symbol": r["symbol"],
                "as_of_date": r["as_of_date"].date().isoformat(),
                "rank": r["rank"],
                "composite_score": r["composite_score"],
                "factors": r["factors"],
                "reasons": r["reasons"],
            }
            for r in ranked[:top_n]
        ],
        "universe_size": len(ranked),
    }
