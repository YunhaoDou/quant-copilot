"""离线回归测试：时间边界、配置、成交和数据源隔离。"""
import pytest

from app.cycle.engine import event_study, load_config, snapshots
from app.cycle.providers import AkShareDataProvider, CSVDataProvider, MockDataProvider


def test_deterministic_mock():
    assert MockDataProvider().daily().equals(MockDataProvider().daily())


def test_no_future_information():
    config = load_config()
    frame = MockDataProvider().daily()
    date = sorted(frame.date.unique())[50]
    cutoff = date + "T15:00:00+08:00"
    truncated = snapshots(frame[frame.date <= date], cutoff, config)
    assert snapshots(frame, cutoff, config) == truncated
    changed = frame.copy()
    changed.loc[changed.date > date, "close"] *= 100
    assert snapshots(changed, cutoff, config) == truncated
    assert snapshots(frame, date + "T14:59:00+08:00", config)[-1]["date"] < date


def test_config_changes_signals():
    config = load_config()
    frame = MockDataProvider().daily()
    strict = snapshots(frame, "2026-12-31T15:00:00+08:00", config)
    loose = snapshots(frame, "2026-12-31T15:00:00+08:00", {**config, "sector_start_pct": -100, "sector_start_limit_up_count": 1})
    assert sum(s["started"] for d in loose for s in d["sectors"]) > sum(s["started"] for d in strict for s in d["sectors"])


def test_empty_history():
    assert snapshots(MockDataProvider().daily(), "2020-01-01T15:00:00+08:00", load_config()) == []


def test_csv_roundtrip_and_validation(tmp_path):
    frame = MockDataProvider(days=3).daily()
    frame.to_csv(tmp_path / "daily.csv", index=False)
    assert len(CSVDataProvider(tmp_path).daily()) == len(frame)
    frame.drop(columns="available_at").to_csv(tmp_path / "daily.csv", index=False)
    with pytest.raises(ValueError, match="缺少字段"):
        CSVDataProvider(tmp_path).daily()


def test_real_provider_never_silently_uses_mock():
    with pytest.raises(ValueError, match="不提供伪造历史"):
        AkShareDataProvider().daily()


def test_t_plus_one_cost_and_nonnegative_cash_equity():
    config = load_config()
    frame = MockDataProvider().daily()
    history = snapshots(frame, "2026-12-31T15:00:00+08:00", config)
    result = event_study(frame, history, config, "持续观察", 1)
    for trade in result["simulation"]["trades"]:
        if trade["status"] == "已平仓":
            assert trade["exit_date"] > trade["entry_date"] > trade["signal_date"]
    assert all(r["equity"] >= 0 for r in result["simulation"]["curve"])
    assert result["simulation"]["max_drawdown"] <= 0


def test_missing_forward_returns_not_counted():
    config = load_config()
    frame = MockDataProvider(days=2).daily()
    history = snapshots(frame, "2026-12-31T15:00:00+08:00", config)
    result = event_study(frame, history, config, history[-1]["card"]["pattern"], 5)
    assert result["summary"]["samples"] == 0
    assert result["summary"]["win_rate"] is None


def test_limit_up_open_rejected():
    config = load_config()
    frame = MockDataProvider(days=5).daily()
    dates = sorted(frame.date.unique())
    symbol = frame.iloc[0].symbol
    history = [{"date": dates[0], "state": "启动", "card": {"pattern": "测试"}, "leaders": [{"symbol": symbol, "sector": "测试板块"}]}]
    frame.loc[(frame.date == dates[1]) & (frame.symbol == symbol), "open"] = frame.loc[(frame.date == dates[1]) & (frame.symbol == symbol), "upper_limit"]
    result = event_study(frame, history, config, "测试", 1)
    assert result["simulation"]["trades"][0]["status"] == "开盘涨停，保守不成交"


def test_limit_down_exit_deferred():
    config = load_config()
    frame = MockDataProvider(days=5).daily()
    dates = sorted(frame.date.unique())
    symbol = frame.iloc[0].symbol
    history = [{"date": dates[0], "state": "启动", "card": {"pattern": "测试"}, "leaders": [{"symbol": symbol, "sector": "测试板块"}]}]
    frame.loc[(frame.date == dates[2]) & (frame.symbol == symbol), "open"] = frame.loc[(frame.date == dates[2]) & (frame.symbol == symbol), "lower_limit"]
    result = event_study(frame, history, config, "测试", 1)
    closed = [t for t in result["simulation"]["trades"] if t["status"] == "已平仓"]
    assert closed and closed[0]["exit_date"] > dates[2]


def test_cost_reduces_equity():
    config = load_config()
    frame = MockDataProvider(days=5).daily()
    dates = sorted(frame.date.unique())
    symbol = frame.iloc[0].symbol
    history = [{"date": dates[0], "state": "启动", "card": {"pattern": "测试"}, "leaders": [{"symbol": symbol, "sector": "测试板块"}]}]
    free = event_study(frame, history, {**config, "buy_cost_bps": 0, "sell_cost_bps": 0, "slippage_bps": 0}, "测试", 1)
    paid = event_study(frame, history, config, "测试", 1)
    assert paid["simulation"]["final_equity"] < free["simulation"]["final_equity"]
