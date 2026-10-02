"""Fund-flow signal: a quantitative proxy for "is institutional money buying or selling"
this US ticker, computed entirely from OHLCV we already have (no new data source, no LLM).

Primary signal is Chaikin Money Flow (CMF) — positive means buying pressure dominated the
window, negative means selling pressure did. It's corroborated by the share of large-volume
days that closed up, and by OBV's short-term trend direction.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FundFlowSignal
from app.services.data_ingestion import load_ohlcv

CMF_WINDOW = 20
MFI_WINDOW = 14
LARGE_VOLUME_MULTIPLE = 1.5
MIN_WINDOW_DAYS = 20

SIGNAL_THRESHOLDS = (
    (40, "strong_inflow"),
    (10, "inflow"),
    (-10, "neutral"),
    (-40, "outflow"),
)


@dataclass
class FundFlowResult:
    symbol: str
    as_of_date: pd.Timestamp
    signal: str
    score: float
    cmf: float
    mfi: float
    obv_trend: str
    large_volume_bias: float
    window_days: int
    method: str = "cmf_mfi_obv_v1"


def _chaikin_money_flow(df: pd.DataFrame, window: int) -> pd.Series:
    high_low = (df["high"] - df["low"]).replace(0, np.nan)
    multiplier = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / high_low
    multiplier = multiplier.fillna(0.0)
    money_flow_volume = multiplier * df["volume"]
    return money_flow_volume.rolling(window).sum() / df["volume"].rolling(window).sum()


def _money_flow_index(df: pd.DataFrame, window: int) -> pd.Series:
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    raw_money_flow = typical_price * df["volume"]
    direction = typical_price.diff()
    positive_flow = raw_money_flow.where(direction > 0, 0.0).rolling(window).sum()
    negative_flow = raw_money_flow.where(direction < 0, 0.0).rolling(window).sum()
    money_ratio = positive_flow / negative_flow.replace(0, np.nan)
    mfi = 100 - (100 / (1 + money_ratio))
    return mfi.fillna(100.0)  # no negative flow in window -> maximally bullish


def _on_balance_volume(df: pd.DataFrame) -> pd.Series:
    direction = np.sign(df["close"].diff()).fillna(0.0)
    return (direction * df["volume"]).cumsum()


def _obv_trend(obv: pd.Series, window: int) -> str:
    tail = obv.tail(window)
    if len(tail) < 2:
        return "flat"
    x = np.arange(len(tail))
    slope = np.polyfit(x, tail.values, 1)[0]
    obv_scale = tail.abs().max() or 1.0
    normalized = slope / obv_scale
    if normalized > 1e-4:
        return "up"
    if normalized < -1e-4:
        return "down"
    return "flat"


def _large_volume_bias(df: pd.DataFrame, window: int, multiple: float) -> float:
    tail = df.tail(window)
    avg_volume = tail["volume"].mean()
    large_days = tail[tail["volume"] > avg_volume * multiple]
    if large_days.empty:
        return 0.5
    up_days = (large_days["close"] > large_days["open"]).sum()
    return float(up_days / len(large_days))


def _classify(score: float) -> str:
    for threshold, label in SIGNAL_THRESHOLDS:
        if score >= threshold:
            return label
    return "strong_outflow"


def compute_fund_flow(df: pd.DataFrame, symbol: str) -> FundFlowResult:
    """Pure function: OHLCV DataFrame (indexed by date, ascending) -> FundFlowResult."""
    if len(df) < MIN_WINDOW_DAYS:
        raise ValueError(
            f"{symbol}: need at least {MIN_WINDOW_DAYS} trading days of price history, got {len(df)}"
        )

    cmf = float(_chaikin_money_flow(df, CMF_WINDOW).iloc[-1])
    mfi = float(_money_flow_index(df, MFI_WINDOW).iloc[-1])
    obv = _on_balance_volume(df)
    obv_trend = _obv_trend(obv, CMF_WINDOW)
    bias = _large_volume_bias(df, CMF_WINDOW, LARGE_VOLUME_MULTIPLE)

    score = cmf * 100
    if bias > 0.6 and cmf > 0:
        score *= 1.2
    elif bias < 0.4 and cmf < 0:
        score *= 1.2
    score = float(np.clip(score, -100, 100))

    return FundFlowResult(
        symbol=symbol,
        as_of_date=df.index[-1],
        signal=_classify(score),
        score=round(score, 2),
        cmf=round(cmf, 4),
        mfi=round(mfi, 2),
        obv_trend=obv_trend,
        large_volume_bias=round(bias, 4),
        window_days=CMF_WINDOW,
    )


async def get_fund_flow_signal(session: AsyncSession, symbol: str) -> dict:
    """Computes the signal from stored price history and upserts it into fund_flow_signals."""
    symbol = symbol.upper()
    df = await load_ohlcv(session, symbol)
    result = compute_fund_flow(df, symbol)

    existing = (
        await session.execute(
            select(FundFlowSignal).where(
                FundFlowSignal.ticker_symbol == symbol,
                FundFlowSignal.as_of_date == result.as_of_date.date(),
            )
        )
    ).scalar_one_or_none()

    if existing is None:
        existing = FundFlowSignal(ticker_symbol=symbol, as_of_date=result.as_of_date.date())
        session.add(existing)

    existing.signal = result.signal
    existing.score = result.score
    existing.cmf = result.cmf
    existing.mfi = result.mfi
    existing.obv_trend = result.obv_trend
    existing.large_volume_bias = result.large_volume_bias
    existing.window_days = result.window_days
    existing.method = result.method
    await session.commit()

    return {
        "symbol": result.symbol,
        "as_of_date": result.as_of_date.date().isoformat(),
        "signal": result.signal,
        "score": result.score,
        "cmf": result.cmf,
        "mfi": result.mfi,
        "obv_trend": result.obv_trend,
        "large_volume_bias": result.large_volume_bias,
        "window_days": result.window_days,
        "method": result.method,
    }
