"""影子账户只使用后续行情，执行成本、T+1及等待约束。"""
import copy
from app.cycle.engine import load_config
from app.cycle.strategy_sim import new_account, step, price_limit


def account():
    value = new_account(load_config())
    value["created_at"] = "2026-11-11T09:00:00+08:00"
    return value


def event(clock="10:00:00", day="2026-11-11", new_low=True, price=10):
    stamp = f"{day}T{clock}+08:00"
    quote = {"code": "600001", "name": "模拟样本", "price": price, "previous_close": 10, "quote_time": stamp}
    return {
        "id": "test", "status": "active", "stage": "启动观察", "dates": [day],
        "first": {"market": {"new_low": new_low}},
        "latest": {"quote_time": stamp, "market": {"risk": "关注"}, "sector": {"started": True},
                   "leaders": [{"symbol": "600001"}], "watched": [{"symbol": "600001", "quote": quote}]},
    }


def test_missing_precondition_never_creates_a_trade_and_processing_is_idempotent():
    a = account()
    step(a, [event(new_low=None)])
    assert a["pending"] is None and not a["trades"]
    assert "等待" in a["decisions"][0]["text"]
    size = len(a["decisions"])
    step(a, [event(new_low=None)])
    assert len(a["decisions"]) == size


def test_signal_uses_next_quote_and_t_plus_one_waits_for_actual_next_day():
    a = account()
    step(a, [event()])
    assert a["pending"]["side"] == "buy" and not a["trades"]
    step(a, [event(clock="10:01:00")])
    assert len(a["trades"]) == 1 and a["position"]["quantity"] % 100 == 0
    assert a["cash"] < a["capital"] and a["position"]["cost"] > 10*a["position"]["quantity"]
    step(a, [event(clock="10:02:00", price=9.1)])
    assert a["pending"]["side"] == "sell"
    step(a, [event(clock="10:03:00", price=9.1)])
    assert len(a["trades"]) == 1
    step(a, [event(day="2026-11-12", price=9.1)])
    assert len(a["trades"]) == 2 and a["trades"][1]["pnl"] < 0
    assert a["position"] is None


def test_limit_up_does_not_fill_and_risk_cancels_buy():
    a = account()
    step(a, [event()])
    step(a, [event(clock="10:01:00", price=11)])
    assert not a["trades"] and a["pending"]
    updated = event(clock="10:02:00")
    updated["latest"]["market"]["risk"] = "高"
    step(a, [updated])
    assert not a["trades"] and a["pending"] is None
    assert price_limit({"code": "300001", "name": "测试", "previous_close": 10}) == (8, 12)


def test_review_uses_only_prior_window_and_keeps_live_account_unchanged(tmp_path, monkeypatch):
    import pandas as pd
    from datetime import datetime, timedelta
    from app.cycle import events, market, strategy_sim
    from app.cycle.live import TZ
    today = datetime.now(TZ).date()
    dates = pd.bdate_range(end=today-timedelta(days=1), periods=20)
    rows = [{"trade_date": d.date().isoformat(), "low": 90, "close": 95} for d in dates]
    rows.extend([
        {"trade_date": today.isoformat(), "low": 100, "close": 105},
        {"trade_date": (today+timedelta(days=1)).isoformat(), "low": 1, "close": 2},
    ])
    monkeypatch.setattr(events, "DB_PATH", tmp_path / "review.sqlite")
    monkeypatch.setattr(market, "fetch_daily", lambda *args: pd.DataFrame(rows))
    result = strategy_sim.review_today()
    assert result["action"] == "不交易"
    assert result["previous_low"] == 90 and result["today_low"] == 100
    with events.database() as db:
        assert strategy_sim.read(db) is None
        assert db.execute("SELECT COUNT(*) FROM strategy_reviews").fetchone()[0] == 1
