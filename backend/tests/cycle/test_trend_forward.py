"""第七策略前向模拟：合成测试样本不进入真实账户。"""
from datetime import datetime
from app.cycle import events, trend_forward as t
from app.cycle.engine import load_config
from app.cycle.strategy_sim import new_account


def package(clock="10:00:00", day="2026-11-11", decision="BUY_CANDIDATE",price=10):
    stamp=f"{day}T{clock}+08:00"
    return {"quote":{"code":"600001","name":"合成测试样本","price":price,"previous_close":10,"quote_time":stamp},
        "result":{"decision":decision,"position_cap_pct":25,"audit_log_id":"synthetic-test"},
        "source":{"fetched_at":stamp}}


def advance(a,p):
    t.advance(a,p,datetime.fromisoformat(p["quote"]["quote_time"]),load_config())


def account():
    a=new_account(load_config());a["created_at"]="2026-11-11T09:00:00+08:00";a["rules"]["sim_stop_loss_pct"]=5
    return a


def test_forward_fill_fixed_stop_and_t_plus_one():
    a=account();advance(a,package())
    assert a["pending"]["side"]=="buy" and not a["trades"]
    advance(a,package(clock="10:01:00"))
    assert len(a["trades"])==1
    fixed=a["position"]["stop_loss_price"]
    assert fixed==a["position"]["entry_price"]*.95
    advance(a,package(clock="10:02:00",decision="EXIT",price=9.4))
    assert a["pending"]["side"]=="sell" and a["position"]["stop_loss_price"]==fixed
    advance(a,package(clock="10:03:00",decision="EXIT",price=9.4))
    assert len(a["trades"])==1
    advance(a,package(day="2026-11-12",decision="EXIT",price=9.4))
    assert len(a["trades"])==2 and a["position"] is None


def test_unknown_and_disappearing_signal_never_fills():
    a=account();advance(a,package(decision="REJECT"));assert not a["pending"]
    advance(a,package(clock="10:01:00"));assert a["pending"]
    advance(a,package(clock="10:02:00",decision="WAIT"));assert not a["pending"] and not a["trades"]


def test_late_or_future_or_after_hours_quotes_do_not_trade():
    for clock in ("08:00:00","16:00:00"):
        a=account();advance(a,package(clock=clock));assert not a["pending"]
    a=account();p=package()
    t.advance(a,p,datetime.fromisoformat("2026-11-11T09:59:00+08:00"),load_config())
    assert not a["pending"]


def test_private_account_persists_and_controls_do_not_reset(tmp_path,monkeypatch):
    monkeypatch.setattr(events,"DB_PATH",tmp_path/"forward.sqlite")
    first=t.control("start")["account"]
    assert first["capital"]==100000
    t.track("600519");t.track("600519")
    assert t.status()["symbols"]==1
    assert t.control("pause")["account"]["status"]=="paused"
    assert t.control("start")["account"]["created_at"]==first["created_at"]


def test_capture_requires_real_fresh_evidence_and_deduplicates(tmp_path,monkeypatch):
    monkeypatch.setattr(events,"DB_PATH",tmp_path/"capture.sqlite")
    from datetime import timedelta
    now=datetime.now(t.TZ)
    result={"current":{"trend_evidence":{"leaders":[{"symbol":"600001"}],"sectors":[]}},"metadata":{"quote_time":now.isoformat()}}
    t.capture(result);t.capture(result)
    assert t.status()["capture_count"]==1
    assert t.status()["symbols"]==1
    result["metadata"]["quote_time"]=(now+timedelta(minutes=1)).isoformat()
    t.capture(result);assert t.status()["capture_count"]==1


def test_trend_does_not_inherit_fixed_take_profit():
    a=account();advance(a,package());advance(a,package(clock="10:01:00"))
    p=package(day="2026-11-12",decision="HOLD",price=11.8)
    p["quote"]["previous_close"]=11.5
    advance(a,p)
    assert a["position"] and not a["pending"]
