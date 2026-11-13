"""第八策略只按事前规则和后续报价模拟；全部使用合成数据。"""
from datetime import datetime,timedelta
import copy
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.cycle import shibor_sim as s,events
from app.cycle.engine import load_config
from app.cycle.live import TZ


def at(text):return datetime.fromisoformat(text).replace(tzinfo=TZ)
def account():return s.new_account(at("2026-11-13T10:00:00"),load_config())
def quotes(stamp="2026-11-13T10:00:20+08:00",p1=1.,p2=2.):
    return {c:dict(code=c,name=c,price=p,previous_close=p,volume_lots=100000,quote_time=stamp) for c,p in [("512890",p1),("159915",p2)]}
def feed():
    ds=pd.bdate_range(end="2026-11-30",periods=1000)
    return {"rows":[dict(date=str(d.date()),rate=2-i*.001) for i,d in enumerate(ds)]}


def test_signal_uses_only_cutoff_and_requires_full_history():
    a=account();r=feed()["rows"];cutoff="2026-10-31"
    out=s.signal(r,cutoff,a["rules"])
    changed=copy.deepcopy(r)
    for row in changed:
        if row["date"]>cutoff:row["rate"]=99
    assert s.signal(changed,cutoff,a["rules"])==out
    assert out["dividend_weight"]==0 and out["growth_weight"]==1
    with pytest.raises(ValueError,match="历史不足"):s.signal(r[-10:],"2026-11-30",a["rules"])


def test_initial_waits_for_new_quote_cash_lots_fee_and_no_duplicate():
    a=account();now=at("2026-11-13T10:00:10")
    s.step(a,quotes("2026-11-13T09:59:59+08:00"),now,feed(),[])
    assert not a["trades"] and a["cash"]==100000
    now=at("2026-11-13T10:00:30");s.step(a,quotes(),now,feed(),[])
    assert len(a["trades"])==2 and a["cash"]>=0 and a["fees"]>0
    assert all(t["quantity"]%100==0 and t["time"]>a["created_at"] and t["fee"]>=5 for t in a["trades"])
    before=copy.deepcopy(a["trades"]);s.step(a,quotes(),now,feed(),[]);assert a["trades"]==before
    assert a["pending"] is None and a["equity"]<100000


def test_t_plus_one_and_price_limit_prevent_impossible_fills():
    a=account();now=at("2026-11-13T10:00:30");s.step(a,quotes(),now,feed(),[])
    a["pending"]=dict(kind="exit",created_at="2026-11-13T10:00:31+08:00",dividend_weight=0.,growth_weight=0.,reason="test")
    s.step(a,quotes("2026-11-13T10:00:40+08:00"),at("2026-11-13T10:00:45"),feed(),[])
    assert len(a["trades"])==2 and a["pending"]
    q=quotes("2026-11-16T10:00:40+08:00");q["512890"].update(price=.9,previous_close=1.)
    s.step(a,q,at("2026-11-16T10:00:45"),feed(),[])
    assert "512890" in a["positions"] and a["pending"]
    s.step(a,quotes("2026-11-16T10:01:40+08:00"),at("2026-11-16T10:01:45"),feed(),[])
    assert not a["positions"] and not a["pending"] and a["cash"]>0


def test_monthly_order_committed_before_close_executes_once():
    a=account();s.step(a,quotes(),at("2026-11-13T10:00:30"),feed(),[])
    now=at("2026-12-01T10:00:30");s.step(a,quotes("2026-12-01T10:00:20+08:00"),now,feed(),[])
    assert a["pending"]["kind"]=="monthly" and len(a["trades"])==2
    s.step(a,quotes("2026-12-01T15:00:00+08:00"),at("2026-12-01T15:00:20"),feed(),["2026-12-01"])
    assert a["pending"] is None and set(a["positions"])=={"159915"}
    trades=copy.deepcopy(a["trades"]);s.step(a,quotes("2026-12-01T15:00:00+08:00"),at("2026-12-01T15:00:30"),feed(),["2026-12-01"]);assert a["trades"]==trades


def test_missed_month_close_is_not_backfilled():
    a=account();s.step(a,quotes(),at("2026-11-13T10:00:30"),feed(),[])
    s.step(a,quotes("2026-12-02T10:00:20+08:00"),at("2026-12-02T10:00:30"),feed(),["2026-12-01"])
    assert len(a["trades"])==2 and not a["pending"] and "错过" in a["decisions"][-1]["text"]


def test_drawdown_schedules_future_quote_exit_and_pauses():
    a=account();s.step(a,quotes(),at("2026-11-13T10:00:30"),feed(),[])
    q=quotes("2026-11-16T10:00:20+08:00",.7,1.4)
    s.step(a,q,at("2026-11-16T10:00:30"),feed(),[])
    assert a["risk_exit"] and a["pending"] and len(a["trades"])==2
    q=quotes("2026-11-16T10:01:20+08:00",.7,1.4)
    s.step(a,q,at("2026-11-16T10:01:30"),feed(),[])
    assert a["status"]=="risk_paused" and not a["positions"]


def test_cash_dividend_once_and_unknown_split_halts():
    a=account();s.step(a,quotes(),at("2026-11-13T10:00:30"),feed(),[]);cash=a["cash"]
    event={"512890":[dict(date="2026-11-16",text="分红：每份派现金0.02元")]}
    s.apply_actions(a,event,at("2026-11-16T10:00:00"));assert a["cash"]==cash+a["positions"]["512890"]["quantity"]*.02
    cash=a["cash"];s.apply_actions(a,event,at("2026-11-16T10:01:00"));assert a["cash"]==cash
    with pytest.raises(ValueError,match="暂停撮合"):s.apply_actions(a,{"512890":[dict(date="2026-11-17",text="拆分：份额折算")]},at("2026-11-17T10:00:00"))


def test_account_control_restart_preserves_rules_cash_and_trades(tmp_path,monkeypatch):
    monkeypatch.setattr(events,"DB_PATH",tmp_path/"paper.sqlite")
    monkeypatch.setattr(s._executor,"submit",lambda *args:None)
    app=FastAPI();app.include_router(s.router);client=TestClient(app)
    a=client.post("/shibor-sim/start").json()["account"]
    client.post("/shibor-sim/pause");b=client.post("/shibor-sim/start").json()["account"]
    assert a["created_at"]==b["created_at"] and a["cash"]==b["cash"] and a["rules"]==b["rules"]
    assert client.get("/shibor-sim").json()["account"]["capital"]==100000


def test_pause_during_fetch_is_respected_without_overwriting_account(tmp_path,monkeypatch):
    monkeypatch.setattr(events,"DB_PATH",tmp_path/"pause.sqlite")
    monkeypatch.setattr(s._executor,"submit",lambda *args:None)
    s.control("start")
    def incoming(now):
        s.control("pause")
        return feed()
    monkeypatch.setattr(s,"rates",incoming)
    monkeypatch.setattr(s,"fetch_quotes",lambda codes:{"quotes":list(quotes().values())})
    monkeypatch.setattr(s,"actions",lambda code,now:[])
    s.run_once()
    a=s.status()["account"]
    assert a["status"]=="paused" and not a["trades"] and a["cash"]==100000


def test_manual_exit_can_pause_without_being_mislabelled_risk_breach():
    a=account();s.step(a,quotes(),at("2026-11-13T10:00:30"),feed(),[])
    a["risk_exit"]=True
    a["pending"]=dict(kind="exit",created_at="2026-11-13T10:00:31+08:00",dividend_weight=0.,growth_weight=0.,reason="manual")
    s.step(a,quotes("2026-11-16T10:00:40+08:00"),at("2026-11-16T10:00:45"),feed(),[])
    assert a["status"]=="paused" and not a["risk_exit"] and not a.get("risk_triggered")


def test_exit_does_not_wait_for_unheld_etf_quote():
    a=account();a["pending"]["dividend_weight"]=0.;a["pending"]["growth_weight"]=1.
    q=quotes();del q["512890"]
    s.step(a,q,at("2026-11-13T10:00:30"),feed(),[])
    assert set(a["positions"])=={"159915"}
    a["risk_exit"]=True;a["risk_triggered"]=True
    a["pending"]=dict(kind="risk",created_at="2026-11-13T10:00:31+08:00",dividend_weight=0.,growth_weight=0.,reason="risk")
    q=quotes("2026-11-16T10:00:40+08:00");del q["512890"]
    s.step(a,q,at("2026-11-16T10:00:45"),feed(),[])
    assert not a["positions"] and a["status"]=="risk_paused"
