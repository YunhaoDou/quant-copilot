"""Fund-flow signal tests. Synthetic OHLCV series (no network), so CMF/MFI/OBV/signal
classification is fully deterministic."""
from datetime import date, timedelta

import pandas as pd
import pytest

from app.models import Price, Ticker
from app.services import fund_flow


def _ohlcv_df(rows: list[dict]) -> pd.DataFrame:
    idx = pd.DatetimeIndex([r["date"] for r in rows])
    return pd.DataFrame(
        {
            "open": [r["open"] for r in rows],
            "high": [r["high"] for r in rows],
            "low": [r["low"] for r in rows],
            "close": [r["close"] for r in rows],
            "volume": [r["volume"] for r in rows],
        },
        index=idx,
    )


def _rising_accumulation(n: int = 25) -> pd.DataFrame:
    """Price grinds up, closes near the day's high, heaviest volume on up days."""
    base = date(2026, 1, 1)
    rows = []
    price = 100.0
    for i in range(n):
        price += 1.0
        rows.append(
            {
                "date": base + timedelta(days=i),
                "open": price - 0.8,
                "high": price + 0.2,
                "low": price - 1.0,
                "close": price,  # closes near the high -> positive money-flow multiplier
                "volume": 2_000_000.0,
            }
        )
    return _ohlcv_df(rows)


def _falling_distribution(n: int = 25) -> pd.DataFrame:
    """Price grinds down, closes near the day's low, heaviest volume on down days."""
    base = date(2026, 1, 1)
    rows = []
    price = 150.0
    for i in range(n):
        price -= 1.0
        rows.append(
            {
                "date": base + timedelta(days=i),
                "open": price + 0.8,
                "high": price + 1.0,
                "low": price - 0.2,
                "close": price,  # closes near the low -> negative money-flow multiplier
                "volume": 2_000_000.0,
            }
        )
    return _ohlcv_df(rows)


def _flat_low_volume(n: int = 25) -> pd.DataFrame:
    """Price chops sideways around a midpoint with unremarkable volume."""
    base = date(2026, 1, 1)
    rows = []
    for i in range(n):
        wiggle = 0.3 if i % 2 == 0 else -0.3
        price = 100.0 + wiggle
        rows.append(
            {
                "date": base + timedelta(days=i),
                "open": 100.0,
                "high": 100.6,
                "low": 99.4,
                "close": price,
                "volume": 500_000.0,
            }
        )
    return _ohlcv_df(rows)


def test_accumulation_pattern_signals_inflow():
    df = _rising_accumulation()
    result = fund_flow.compute_fund_flow(df, "AAA")
    assert result.cmf > 0
    assert result.signal in ("inflow", "strong_inflow")
    assert result.score > 0
    assert result.obv_trend == "up"


def test_distribution_pattern_signals_outflow():
    df = _falling_distribution()
    result = fund_flow.compute_fund_flow(df, "BBB")
    assert result.cmf < 0
    assert result.signal in ("outflow", "strong_outflow")
    assert result.score < 0
    assert result.obv_trend == "down"


def test_flat_low_volume_is_neutral():
    df = _flat_low_volume()
    result = fund_flow.compute_fund_flow(df, "CCC")
    assert result.signal == "neutral"
    assert abs(result.score) <= 10


def test_insufficient_history_raises():
    df = _rising_accumulation(n=5)
    with pytest.raises(ValueError, match="need at least"):
        fund_flow.compute_fund_flow(df, "DDD")


def test_cmf_hand_computed_three_bar_window():
    # 3 bars, window=3: bar1 multiplier=1 (close==high), bar2 multiplier=-1 (close==low),
    # bar3 multiplier=0 (close==midpoint). Volumes equal -> CMF = (1*v -1*v +0*v)/3v = 0.
    rows = [
        {"date": date(2026, 1, 1), "open": 9, "high": 10, "low": 8, "close": 10, "volume": 100.0},
        {"date": date(2026, 1, 2), "open": 10, "high": 10, "low": 8, "close": 8, "volume": 100.0},
        {"date": date(2026, 1, 3), "open": 9, "high": 10, "low": 8, "close": 9, "volume": 100.0},
    ]
    df = _ohlcv_df(rows)
    cmf_series = fund_flow._chaikin_money_flow(df, window=3)
    assert cmf_series.iloc[-1] == pytest.approx(0.0, abs=1e-9)


async def _seed_ticker_with_prices(session, symbol: str, df: pd.DataFrame):
    session.add(Ticker(symbol=symbol, name=f"{symbol} Inc.", market="US"))
    await session.flush()
    for trade_date, row in df.iterrows():
        session.add(
            Price(
                ticker_symbol=symbol,
                trade_date=trade_date.date(),
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
            )
        )
    await session.commit()


@pytest.mark.asyncio
async def test_get_fund_flow_signal_persists_row(db_session):
    df = _rising_accumulation()
    await _seed_ticker_with_prices(db_session, "AAA", df)

    payload = await fund_flow.get_fund_flow_signal(db_session, "aaa")  # lower-case in, upper-case out
    assert payload["symbol"] == "AAA"
    assert payload["signal"] in ("inflow", "strong_inflow")
    assert payload["method"] == "cmf_mfi_obv_v1"

    # calling again (same latest date) upserts rather than duplicating
    payload2 = await fund_flow.get_fund_flow_signal(db_session, "AAA")
    assert payload2["as_of_date"] == payload["as_of_date"]


@pytest.mark.asyncio
async def test_get_fund_flow_signal_no_history_raises(db_session):
    session = db_session
    session.add(Ticker(symbol="ZZZ", name="ZZZ Inc.", market="US"))
    await session.commit()
    with pytest.raises(ValueError, match="need at least"):
        await fund_flow.get_fund_flow_signal(session, "ZZZ")
