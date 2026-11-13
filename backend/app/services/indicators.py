"""Shared return/risk metric primitives (pure pandas/numpy, no I/O, no rounding).

Call sites keep their own externally visible conventions (rounding, JSON field names,
windows, risk-free rate); this module only centralizes the math so the same formula is
not re-implemented five times. Callers pass the convention explicitly instead of this
module silently picking one.

Conventions
-----------
* A **value series** is a price / NAV / equity curve ordered by observation time.
  A **return series** is the period-over-period simple return of a value series
  (``value.pct_change().dropna()``), expressed as a fraction: 0.01 == +1%.
* Every metric below returns a **fraction**, never a percent: ``total_return`` 0.10 is
  +10%, ``annualized_volatility`` 0.20 is 20%/yr, ``max_drawdown`` -0.25 is -25%,
  ``win_rate`` 0.55 is 55%. Call sites multiply by 100 where their JSON reports percent.
* ``risk_free`` is an **annualized fraction** (0.02 == 2%/yr); Sharpe/Sortino divide it by
  ``periods_per_year`` internally.
* ``periods_per_year`` defaults to 252 trading days; pass e.g. 52 or 12 for other
  sampling frequencies.
* ``annualized_return`` is CAGR: ``(last/first) ** (periods_per_year / periods) - 1``.
  ``periods`` defaults to ``len(values) - 1`` (one period per price change); pass
  ``periods=len(values)`` for the "first observation also counts as a period" convention.
* Sharpe = annualized arithmetic mean excess return / annualized sample (ddof=1)
  volatility; risk-free is compared against the mean, not subtracted from each return.
* Sortino's downside risk is the root-mean-square of negative excess returns over the
  **whole** sample (``sqrt(mean(min(r - rf/period, 0)**2)) * sqrt(periods_per_year)``),
  not the standard deviation of only the negative observations.
* ``sharpe``/``sortino`` return ``None`` when the risk denominator is exactly zero; a NaN
  denominator is propagated (callers that display raw floats already handle NaN).
* ``max_drawdown`` is measured from the running peak of the value series: the minimum of
  ``value / value.cummax() - 1`` (negative or zero).
* ``value_at_risk``/``conditional_value_at_risk`` return a positive loss magnitude as a
  fraction of the value (``0.03`` means a 3% loss); the quantile uses pandas' default
  linear interpolation and CVaR is the mean of returns at or below that quantile.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_PERIODS_PER_YEAR = 252
DEFAULT_LEVEL = 0.05


def total_return(values: pd.Series) -> float:
    """Simple return from the first to the last value, as a fraction."""
    return float(values.iloc[-1] / values.iloc[0] - 1)


def annualized_return(
    values: pd.Series,
    periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
    periods: int | None = None,
) -> float:
    """CAGR from the first to the last value, as a fraction.

    ``periods`` is the number of return periods the series covers; it defaults to
    ``len(values) - 1`` (one period per price change).
    """
    if periods is None:
        periods = len(values) - 1
    if periods <= 0:
        raise ValueError("annualized_return needs at least one return period")
    return float((values.iloc[-1] / values.iloc[0]) ** (periods_per_year / periods) - 1)


def annualized_volatility(
    returns: pd.Series, periods_per_year: int = DEFAULT_PERIODS_PER_YEAR
) -> float:
    """Sample (ddof=1) standard deviation of returns, annualized by sqrt(periods_per_year)."""
    return float(returns.std() * np.sqrt(periods_per_year))


def sharpe(
    returns: pd.Series,
    risk_free: float = 0.0,
    periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
) -> float | None:
    """Annualized excess return over annualized volatility (``None`` if volatility is 0)."""
    volatility = annualized_volatility(returns, periods_per_year)
    if volatility == 0:
        return None
    return float((returns.mean() * periods_per_year - risk_free) / volatility)


def sortino(
    returns: pd.Series,
    risk_free: float = 0.0,
    periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
) -> float | None:
    """Annualized excess return over annualized downside deviation (``None`` if downside is 0)."""
    excess = returns - risk_free / periods_per_year
    downside = float(np.sqrt(np.mean(np.minimum(excess, 0) ** 2)) * np.sqrt(periods_per_year))
    if downside == 0:
        return None
    return float((returns.mean() * periods_per_year - risk_free) / downside)


def calmar(annual_return: float, max_drawdown: float) -> float | None:
    """Annual return / |max drawdown| (``None`` when there is no drawdown)."""
    if not max_drawdown:
        return None
    return float(annual_return / abs(max_drawdown))


def max_drawdown(values: pd.Series) -> float:
    """Deepest peak-to-trough decline of the value series, as a negative fraction."""
    return float((values / values.cummax() - 1).min())


def win_rate(returns: pd.Series) -> float:
    """Share of strictly positive return periods, as a fraction in [0, 1]."""
    return float((returns > 0).mean())


def value_at_risk(returns: pd.Series, level: float = DEFAULT_LEVEL) -> float:
    """Positive loss magnitude at ``level`` (default 5%), as a fraction of the value.

    Returns int 0 (not 0.0) when the quantile is non-negative, matching the legacy
    research-lab JSON shape.
    """
    if len(returns) == 0:
        return 0
    return max(0, -float(returns.quantile(level)))


def conditional_value_at_risk(returns: pd.Series, level: float = DEFAULT_LEVEL) -> float:
    """Mean loss beyond the ``level`` quantile (expected shortfall), as a positive fraction.

    Returns int 0 (not 0.0) when there is no loss tail, matching the legacy JSON shape.
    """
    if len(returns) == 0:
        return 0
    tail = returns[returns <= returns.quantile(level)]
    if len(tail) == 0:
        return 0
    return max(0, -float(tail.mean()))


def profit_loss_ratio(returns: pd.Series) -> float | None:
    """Mean winning return / |mean losing return|; ``None`` if either side is empty."""
    gains, losses = returns[returns > 0], returns[returns < 0]
    if len(gains) == 0 or len(losses) == 0:
        return None
    return float(gains.mean() / abs(losses.mean()))
