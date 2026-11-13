"""优化必须保留缓存时间、完整覆盖和账户单执行者边界。"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Event
from time import sleep,perf_counter
import copy
import pandas as pd
from app.cycle import market,events,strategy_center
from app.cycle.engine import load_config


def test_overlapping_quote_requests_fetch_each_code_once(monkeypatch):
    calls=[];monkeypatch.setattr(market,"_cache",{});monkeypatch.setattr(market,"_quote_flights",{})
    def rows(codes,client):
        calls.extend(codes);sleep(.03)
        return [dict(symbol=c,code=c[2:],price=10,quote_time="2026-11-13T10:00:00+08:00") for c in codes]
    monkeypatch.setattr(market,"fetch_quote_rows",rows)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(market.fetch_quotes,["600519","000001"]);b=pool.submit(market.fetch_quotes,["000001","300750"]);pa,pb=a.result(),b.result()
    assert sorted(calls)==["sh600519","sz000001","sz300750"]
    pa["quotes"][0]["price"]=0
    assert market.fetch_quotes(["600519"])["quotes"][0]["price"]==10
    assert market.fetch_quotes(["600519"])["quotes"][0]["quote_time"]=="2026-11-13T10:00:00+08:00"


def test_failed_fetch_can_retry_and_daily_results_are_independent(monkeypatch):
    monkeypatch.setattr(market,"_daily_cache",{});monkeypatch.setattr(market,"_daily_flights",{})
    calls=[]
    def source(*args):
        calls.append(1)
        if len(calls)==1:raise ValueError("temporary")
        return pd.DataFrame(dict(trade_date=["2026-11-12"],close=[10.]))
    monkeypatch.setattr(market,"_fetch_daily_uncached",source)
    try:market.fetch_daily("600519")
    except ValueError:pass
    a=market.fetch_daily("600519");a.loc[0,"close"]=0
    assert market.fetch_daily("600519").close.iloc[0]==10 and len(calls)==2


def test_wal_reader_does_not_wait_for_writer_or_see_uncommitted_data(tmp_path):
    path=tmp_path/"events.sqlite"
    with events.database(path) as db:db.execute("INSERT INTO records VALUES('r','e','d','old')")
    started=Event();release=Event()
    def writer():
        with events.database(path) as db:
            db.execute("BEGIN IMMEDIATE");db.execute("UPDATE records SET payload='new'");started.set();release.wait(2)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(writer);assert started.wait(2)
        t=perf_counter()
        with events.database(path) as db:assert db.execute("SELECT payload FROM records").fetchone()[0]=="old"
        elapsed=perf_counter()-t;release.set();future.result()
    assert elapsed<.5
    with events.database(path) as db:assert db.execute("SELECT payload FROM records").fetchone()[0]=="new"


def test_config_returns_copy_and_account_update_single_owner(monkeypatch):
    a=load_config();a["initial_capital"]=0;assert load_config()["initial_capital"]>0
    calls=[];started=Event();release=Event()
    def run():calls.append(1);started.set();release.wait(2)
    monkeypatch.setattr(strategy_center,"_run_accounts",run)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(strategy_center.run_accounts);assert started.wait(2);second=pool.submit(strategy_center.run_accounts);second.result(timeout=1);release.set();first.result()
    assert calls==[1]


def test_batched_quotes_preserve_every_symbol_and_explicit_failures(monkeypatch):
    codes=[str(600000+i) for i in range(321)]
    def fetch(batch):return {"quotes":[{"code":c} for c in batch]}
    monkeypatch.setattr(market,"fetch_quotes",fetch)
    rows,errors=market.quote_batches(codes)
    assert set(rows)==set(codes) and not errors


def test_existing_experiment_is_read_only_during_account_write(tmp_path,monkeypatch):
    import json
    from app.cycle import experiment
    monkeypatch.setattr(events,"DB_PATH",tmp_path/"accounts.sqlite")
    expected={"start_date":"2026-11-11","scope":"all-a"}
    with events.database() as db:
        db.execute("CREATE TABLE strategy_experiment(id INTEGER PRIMARY KEY,payload TEXT)")
        db.execute("INSERT INTO strategy_experiment VALUES(1,?)",(json.dumps(expected),))
    started=Event();release=Event()
    def writer():
        with events.database() as db:
            db.execute("BEGIN IMMEDIATE");started.set();release.wait(2)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(writer);assert started.wait(2)
        t=perf_counter();assert experiment.setup()==expected
        elapsed=perf_counter()-t;release.set();future.result()
    assert elapsed<.5
