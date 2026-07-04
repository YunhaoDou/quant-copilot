"""Runs strategy templates through vectorbt and reduces results to persistable metrics."""
import itertools

import numpy as np
import pandas as pd
import vectorbt as vbt

from app.services.strategies import STRATEGIES


def _safe_float(value) -> float:
    value = float(value)
    return 0.0 if np.isnan(value) or np.isinf(value) else value


def run_single(close: pd.Series, strategy_key: str, params: dict | None = None) -> dict:
    if strategy_key not in STRATEGIES:
        raise ValueError(f"unknown strategy: {strategy_key}")
    spec = STRATEGIES[strategy_key]
    merged_params = {**spec["default_params"], **(params or {})}

    entries, exits = spec["fn"](close, **merged_params)
    pf = vbt.Portfolio.from_signals(close, entries, exits, init_cash=100_000.0, fees=0.001, freq="1D")

    return {
        "strategy_key": strategy_key,
        "label": spec["label"],
        "params": merged_params,
        "total_return": _safe_float(pf.total_return()),
        "sharpe_ratio": _safe_float(pf.sharpe_ratio()),
        "max_drawdown": _safe_float(pf.max_drawdown()),
        "win_rate": _safe_float(pf.trades.win_rate()) if pf.trades.count() > 0 else 0.0,
        "num_trades": int(pf.trades.count()),
        "equity_curve": pf.value(),
    }


def run_comparison(close: pd.Series) -> list[dict]:
    """Run all 4 strategy templates against the same series for side-by-side comparison."""
    return [run_single(close, key) for key in STRATEGIES]


def run_param_sweep(close: pd.Series, strategy_key: str, param_grid: dict[str, list]) -> list[dict]:
    """Sweep every combination in `param_grid` (e.g. {"fast": [5, 10], "slow": [20, 30]})."""
    keys = list(param_grid.keys())
    combos = list(itertools.product(*param_grid.values()))
    results = []
    for combo in combos:
        params = dict(zip(keys, combo))
        result = run_single(close, strategy_key, params)
        result.pop("equity_curve", None)
        results.append(result)
    return results
