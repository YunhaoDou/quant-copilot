"""Screening tests. Each factor function gets a hand-derived expected value computed with
plain arithmetic (not by re-running the pandas expression under test) so this genuinely
checks numeric correctness, not just "did it return without crashing". rank_universe's
z-score/composite math is likewise hand-verified on a tiny synthetic universe."""
import math
from datetime import date, timedelta

import pandas as pd
import pytest

from app.models import Price, Ticker
from app.services import screening
from app.services.screening import StockFactors, compute_stock_factors, rank_universe


def _ohlcv(rows: list[dict]) -> pd.DataFrame:
    idx = pd.DatetimeIndex([r["date"] for r in rows])
    return pd.DataFrame(
        {k: [r[k] for r in rows] for k in ("open", "high", "low", "close", "volume")},
        index=idx,
    )


def _series_from_closes(closes: list[float], volumes: list[float] | None = None) -> pd.DataFrame:
    base = date(2026, 1, 1)
    volumes = volumes or [1_000_000.0] * len(closes)
    rows = [
        {
            "date": base + timedelta(days=i),
            "open": c,
            "high": c * 1.01,
            "low": c * 0.99,
            "close": c,
            "volume": v,
        }
        for i, (c, v) in enumerate(zip(closes, volumes))
    ]
    return _ohlcv(rows)


# ---- individual factor math, hand-derived expected values ----

def test_rsi_14_hand_computed():
    # 15 closes, diffs alternate +2, -1, +2, -1, ... (14 diffs): gains sum=14 avg=1.0,
    # losses sum=7 avg=0.5 -> RS=2.0 -> RSI = 100 - 100/(1+2) = 66.666...
    closes = [100.0]
    for i in range(14):
        closes.append(closes[-1] + (2 if i % 2 == 0 else -1))
    df = _series_from_closes(closes)
    rsi = screening._rsi_14(df["close"])
    assert rsi == pytest.approx(66.6667, abs=1e-3)


def test_momentum_3m_hand_computed():
    # 64 points so index -1 and index -1-63 both exist; set close[0]=100, close[-1]=110.
    closes = [100.0] + [105.0] * 62 + [110.0]
    df = _series_from_closes(closes)
    mom = screening._return_over(df["close"], 63)
    assert mom == pytest.approx(0.10, abs=1e-9)


def test_momentum_3m_insufficient_history_is_none():
    closes = [100.0] * 10
    df = _series_from_closes(closes)
    assert screening._return_over(df["close"], 63) is None


def test_volatility_20d_hand_computed():
    # Exactly 20 diffs alternating +1%/-1% (10 of each) -> mean return is exactly 0.
    # sample variance = sum(dev^2)/(n-1) = (20 * 0.0001) / 19 ; std = sqrt(that).
    closes = [100.0]
    for i in range(20):
        closes.append(closes[-1] * (1.01 if i % 2 == 0 else 0.99))
    df = _series_from_closes(closes)
    vol = screening._volatility_20d(df["close"])

    expected_std = math.sqrt(20 * (0.01**2) / 19)
    expected_annualized = expected_std * math.sqrt(252)
    assert vol == pytest.approx(expected_annualized, rel=1e-6)


def test_volume_trend_hand_computed():
    # 60 sessions: first 40 at volume 1000, last 20 at volume 2000.
    # vol20 = 2000. vol60 = (40*1000 + 20*2000)/60 = 1333.333 -> ratio = 1.5
    volumes = [1000.0] * 40 + [2000.0] * 20
    closes = [100.0] * 60
    df = _series_from_closes(closes, volumes)
    ratio = screening._volume_trend(df["volume"])
    assert ratio == pytest.approx(1.5, abs=1e-6)


def test_trend_vs_200ma_hand_computed():
    # 200 sessions at 100 except the last at 110.
    # ma200 = (199*100 + 110)/200 = 100.05 -> trend = (110-100.05)/100.05
    closes = [100.0] * 199 + [110.0]
    df = _series_from_closes(closes)
    trend = screening._trend_vs_200ma(df["close"])
    expected = (110.0 - 100.05) / 100.05
    assert trend == pytest.approx(expected, abs=1e-9)


def test_max_drawdown_1y_hand_computed():
    closes = [100.0, 150.0, 75.0]
    df = _series_from_closes(closes)
    dd = screening._max_drawdown_1y(df["close"])
    assert dd == pytest.approx(-0.50, abs=1e-9)


def test_sharpe_like_zero_when_mean_return_is_zero():
    # Exactly 20 diffs alternating +1%/-1% (10 of each) -> mean return is exactly 0.
    closes = [100.0]
    for i in range(20):
        closes.append(closes[-1] * (1.01 if i % 2 == 0 else 0.99))
    df = _series_from_closes(closes)
    sharpe = screening._sharpe_like(df["close"])
    assert sharpe == pytest.approx(0.0, abs=1e-9)


def test_sharpe_like_none_when_flat_zero_variance():
    closes = [100.0] * 30
    df = _series_from_closes(closes)
    assert screening._sharpe_like(df["close"]) is None


# ---- compute_stock_factors: graceful degradation + fund-flow pipe-through ----

def test_compute_stock_factors_missing_long_lookbacks_stay_none():
    # 70 days: momentum_3m(63)/volume_trend(60)/rsi/volatility/sharpe/drawdown/fund_flow all
    # computable; momentum_12m(252) and trend_vs_200ma(200) require more history than we have.
    closes = [100.0 + i * 0.5 for i in range(70)]
    volumes = [1_000_000.0 + i * 1000 for i in range(70)]
    df = _series_from_closes(closes, volumes)
    factors = compute_stock_factors(df, "AAA")

    assert factors.values["momentum_12m"] is None
    assert factors.values["trend_vs_200ma"] is None
    assert factors.values["momentum_3m"] is not None
    assert factors.values["volume_trend"] is not None
    assert factors.values["fund_flow_score"] is not None


def test_compute_stock_factors_fund_flow_score_matches_fund_flow_service():
    from app.services import fund_flow

    closes = [100.0 + i for i in range(30)]
    df = _series_from_closes(closes)
    factors = compute_stock_factors(df, "AAA")
    expected = fund_flow.compute_fund_flow(df, "AAA").score
    assert factors.values["fund_flow_score"] == expected


def test_compute_stock_factors_raises_on_empty_history():
    with pytest.raises(ValueError, match="no price history"):
        compute_stock_factors(pd.DataFrame(columns=["open", "high", "low", "close", "volume"]), "ZZZ")


# ---- rank_universe: hand-derived z-scores on a tiny synthetic universe ----

def test_rank_universe_zscore_and_ranking_hand_derived():
    # Only momentum_3m is populated (everything else None for all three) so composite ==
    # that single factor's z-score. Values 0.30, 0.0, -0.30 -> mean 0, pstdev = sqrt(0.06).
    def factors(symbol, mom):
        vals = dict.fromkeys(screening.FACTOR_DIRECTION, None)
        vals["momentum_3m"] = mom
        return StockFactors(symbol=symbol, as_of_date=pd.Timestamp("2026-06-01"), values=vals)

    universe = [factors("HIGH", 0.30), factors("MID", 0.0), factors("LOW", -0.30)]
    ranked = rank_universe(universe)

    expected_pstdev = math.sqrt(0.06)
    by_symbol = {r["symbol"]: r for r in ranked}
    assert by_symbol["HIGH"]["composite_score"] == pytest.approx(0.30 / expected_pstdev, abs=1e-4)
    assert by_symbol["MID"]["composite_score"] == pytest.approx(0.0, abs=1e-9)
    assert by_symbol["LOW"]["composite_score"] == pytest.approx(-0.30 / expected_pstdev, abs=1e-4)

    assert by_symbol["HIGH"]["rank"] == 1
    assert by_symbol["MID"]["rank"] == 2
    assert by_symbol["LOW"]["rank"] == 3

    assert "3-month momentum" in by_symbol["HIGH"]["reasons"]
    assert by_symbol["LOW"]["reasons"] == []  # negative contribution never surfaces as a "reason"


def test_rank_universe_reasons_localized_to_zh():
    def factors(symbol, mom):
        vals = dict.fromkeys(screening.FACTOR_DIRECTION, None)
        vals["momentum_3m"] = mom
        return StockFactors(symbol=symbol, as_of_date=pd.Timestamp("2026-06-01"), values=vals)

    universe = [factors("HIGH", 0.30), factors("LOW", -0.30)]
    ranked = rank_universe(universe, lang="zh")
    by_symbol = {r["symbol"]: r for r in ranked}
    assert by_symbol["HIGH"]["reasons"] == ["3个月动量"]


def test_rank_universe_factor_present_for_only_one_ticker_gets_zero_zscore():
    def factors(symbol, mom):
        vals = dict.fromkeys(screening.FACTOR_DIRECTION, None)
        vals["momentum_3m"] = mom
        return StockFactors(symbol=symbol, as_of_date=pd.Timestamp("2026-06-01"), values=vals)

    universe = [factors("ONLY", 0.5), factors("NONE_A", None), factors("NONE_B", None)]
    ranked = rank_universe(universe)
    only = next(r for r in ranked if r["symbol"] == "ONLY")
    assert only["composite_score"] == 0.0  # <2 non-null observations -> zscore defined as 0


def test_rank_universe_missing_factor_excluded_from_average_not_treated_as_zero():
    vals_a = dict.fromkeys(screening.FACTOR_DIRECTION, None)
    vals_a["momentum_3m"] = 0.5
    vals_a["sharpe_like"] = None  # missing -> must not drag the average toward 0

    vals_b = dict.fromkeys(screening.FACTOR_DIRECTION, None)
    vals_b["momentum_3m"] = -0.5
    vals_b["sharpe_like"] = None

    universe = [
        StockFactors(symbol="A", as_of_date=pd.Timestamp("2026-06-01"), values=vals_a),
        StockFactors(symbol="B", as_of_date=pd.Timestamp("2026-06-01"), values=vals_b),
    ]
    ranked = rank_universe(universe)
    by_symbol = {r["symbol"]: r for r in ranked}
    # only momentum_3m has 2 non-null values -> z = +/-1.0 (pstdev of [0.5,-0.5] is 0.5)
    assert by_symbol["A"]["composite_score"] == pytest.approx(1.0, abs=1e-9)
    assert by_symbol["B"]["composite_score"] == pytest.approx(-1.0, abs=1e-9)


# ---- full DB integration: run_screening ranks a real synthetic universe correctly ----

def _long_series(n: int, drift_per_day: float, volume_base: float = 1_000_000.0, volume_drift: float = 0.0) -> list[dict]:
    base = date(2025, 1, 1)
    rows = []
    price = 100.0
    for i in range(n):
        price *= 1 + drift_per_day
        rows.append(
            {
                "date": base + timedelta(days=i),
                "open": price * 0.995,
                "high": price * 1.01,
                "low": price * 0.99,
                "close": price,
                "volume": volume_base + i * volume_drift,
            }
        )
    return rows


async def _seed(session, symbol: str, rows: list[dict]):
    session.add(Ticker(symbol=symbol, name=f"{symbol} Inc.", market="US"))
    await session.flush()
    for r in rows:
        session.add(Price(ticker_symbol=symbol, trade_date=r["date"], **{k: r[k] for k in ("open", "high", "low", "close", "volume")}))
    await session.commit()


@pytest.mark.asyncio
async def test_run_screening_ranks_uptrend_above_flat_above_downtrend(db_session):
    await _seed(db_session, "UP", _long_series(300, 0.003, volume_drift=500))       # steady uptrend, rising volume
    await _seed(db_session, "FLAT", _long_series(300, 0.0000))                       # no drift
    await _seed(db_session, "DOWN", _long_series(300, -0.003, volume_drift=500))     # steady downtrend, rising volume
    await _seed(db_session, "SPY", _long_series(300, 0.003))                          # benchmark, must be excluded

    result = await screening.run_screening(db_session, top_n=10)

    assert result["universe_size"] == 3  # SPY excluded
    symbols_in_order = [r["symbol"] for r in result["results"]]
    assert symbols_in_order.index("UP") < symbols_in_order.index("FLAT") < symbols_in_order.index("DOWN")
    assert "SPY" not in symbols_in_order

    up_row = next(r for r in result["results"] if r["symbol"] == "UP")
    assert up_row["factors"]["momentum_3m"] > 0
    assert up_row["factors"]["trend_vs_200ma"] > 0


@pytest.mark.asyncio
async def test_run_screening_persists_stock_scores(db_session):
    from sqlalchemy import select

    from app.models import StockScore

    await _seed(db_session, "UP", _long_series(300, 0.003))
    await _seed(db_session, "DOWN", _long_series(300, -0.003))

    await screening.run_screening(db_session, top_n=10)

    rows = (await db_session.execute(select(StockScore))).scalars().all()
    assert {r.ticker_symbol for r in rows} == {"UP", "DOWN"}
    assert all(r.method == "zscore_9factor_v1" for r in rows)
