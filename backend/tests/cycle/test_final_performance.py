"""剩余性能优化的边界：编码合并、缓存预算、资源预留、事务及连接关闭。"""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import sleep
from uuid import uuid4
import json
import sqlite3
import pytest
from fastapi import HTTPException
from starlette.requests import Request
from app.cycle import read_cache,events
from app.cycle.resources import ResourceGate


def test_identical_response_encodes_once_and_failures_retry(monkeypatch):
    original=read_cache._encode;calls=[];started=Event();release=Event();key=uuid4().hex
    def slow(data):calls.append(1);started.set();release.wait(3);return original(data)
    monkeypatch.setattr(read_cache,'_encode',slow)
    request=Request({'type':'http','headers':[(b'accept-encoding',b'gzip')]})
    with ThreadPoolExecutor(8) as pool:
        first=pool.submit(read_cache.response,{'rows':[1]*10000},request,key);assert started.wait(1)
        others=[pool.submit(read_cache.response,{'rows':[1]*10000},request,key) for _ in range(7)];sleep(.03);release.set()
        results=[first.result(),*[f.result() for f in others]]
    assert calls==[1] and len({r.headers['etag'] for r in results})==1 and len({r.body for r in results})==1
    bad=uuid4().hex
    with pytest.raises(ValueError):read_cache.response({'x':float('nan')},request,bad)
    assert read_cache.response({'x':1},request,bad).status_code==200


def test_conditional_response_and_gzip_exclusion():
    key=uuid4().hex;data={'x':'中'*2000}
    plain=read_cache.response(data,Request({'type':'http','headers':[(b'accept-encoding',b'gzip;q=0, *;q=1')]}),key)
    assert 'content-encoding' not in plain.headers and json.loads(plain.body)==data
    tag=plain.headers['etag'].removeprefix('W/')
    assert read_cache.response(data,Request({'type':'http','headers':[(b'if-none-match',tag.encode())]}),key).status_code==304


def test_budget_eviction_keeps_complete_output_and_never_caches_oversize(monkeypatch,tmp_path):
    monkeypatch.setattr(read_cache,'_MODEL_BUDGET',5000);monkeypatch.setattr(read_cache,'_BODY_BUDGET',1000);monkeypatch.setattr(read_cache,'_DOCUMENT_BUDGET',1000)
    kind=uuid4().hex;current=read_cache.model(kind,'v1',lambda:{'rows':['x'*10000]})
    assert len(current['rows'][0])==10000 and 'v1' not in read_cache._models.get(kind,{})
    r=read_cache.response(current,Request({'type':'http','headers':[]}),uuid4().hex);assert len(json.loads(r.body)['rows'][0])==10000
    path=tmp_path/'large.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE board(id INTEGER PRIMARY KEY,payload TEXT)');db.execute('INSERT INTO board VALUES(1,?)',(json.dumps({'rows':['x'*10000]}),))
    assert len(read_cache.document(path,'board')[0]['rows'][0])==10000
    stats=read_cache.cache_stats()
    assert stats['body_bytes']<=stats['body_budget'] and stats['model_bytes']<=stats['model_budget'] and stats['document_bytes']<=stats['document_budget']
    # 模型未缓存时仍支持当前版本，但不伪造已淘汰的旧版本。
    assert read_cache.versioned(kind,current,current['snapshot_version']) is current
    with pytest.raises(HTTPException):read_cache.versioned(kind,current,'expired')


def test_background_capacity_reserves_foreground_and_releases_after_error():
    gate=ResourceGate(3,2);started=[Event(),Event()];release=Event()
    def bg(i):
        with gate.slot(True):started[i].set();release.wait(3)
    with ThreadPoolExecutor(4) as pool:
        jobs=[pool.submit(bg,i) for i in range(2)];assert all(e.wait(1) for e in started)
        def foreground():
            with gate.slot(False):return 'interactive'
        assert pool.submit(foreground).result(timeout=.5)=='interactive'
        try:
            with gate.slot(False):raise ValueError('test')
        except ValueError:pass
        release.set();[f.result() for f in jobs]
    assert gate.stats()['active']==0 and gate.stats()['background_active']==0


def test_database_commits_rolls_back_and_closes(tmp_path):
    path=tmp_path/'ledger.sqlite'
    with events.database(path) as db:db.execute("INSERT INTO records VALUES('r','e','d','old')")
    with pytest.raises(sqlite3.ProgrammingError):db.execute('SELECT 1')
    with pytest.raises(RuntimeError):
        with events.database(path) as db:
            db.execute("UPDATE records SET payload='wrong'");raise RuntimeError('rollback')
    with events.database(path) as db:assert db.execute('SELECT payload FROM records').fetchone()[0]=='old'


def test_combined_model_budget_evicts_old_version_explicitly(monkeypatch):
    sample={'blob':'x'*1000,'snapshot_version':'v'*24}
    monkeypatch.setattr(read_cache,'_MODEL_BUDGET',read_cache.deep_size(sample)+100)
    kind=uuid4().hex;old=read_cache.model(kind,'one',lambda:{'blob':'x'*1000})
    current=read_cache.model(kind,'two',lambda:{'blob':'y'*1000})
    assert current['blob']=='y'*1000
    stats=read_cache.cache_stats();assert stats['model_bytes']<=stats['model_budget']
    with pytest.raises(HTTPException) as error:read_cache.versioned(kind,current,old['snapshot_version'])
    assert error.value.status_code==409


def test_oversized_daily_frame_returns_all_rows_without_caching(monkeypatch):
    import pandas as pd
    from app.cycle import market
    monkeypatch.setattr(market,'_daily_cache',{});monkeypatch.setattr(market,'_daily_flights',{});monkeypatch.setattr(market,'_daily_budget',1)
    frame=pd.DataFrame({'trade_date':['2026-11-12']*50,'close':[1.]*50})
    monkeypatch.setattr(market,'_fetch_daily_uncached',lambda *args:frame)
    result=market.fetch_daily('600519',50)
    assert result.equals(frame) and not market._daily_cache


def test_document_keeps_digest_not_duplicate_raw_and_detects_same_length_update(tmp_path,monkeypatch):
    path=tmp_path/'compact.sqlite';payload={'rows':['中'*10000]};raw=json.dumps(payload,ensure_ascii=False)
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE board(id INTEGER PRIMARY KEY,payload TEXT)');db.execute('INSERT INTO board VALUES(1,?)',(raw,))
    first,version=read_cache.document(path,'board',ttl=0)
    key=(str(path.resolve()),'board');retained=read_cache._documents[key]
    assert len(retained[3])==64 and retained[3]!=raw
    original=read_cache.json.loads;calls=[]
    def decode(value):calls.append(1);return original(value)
    monkeypatch.setattr(read_cache.json,'loads',decode)
    assert read_cache.document(path,'board',ttl=0)[0] is first and calls==[]
    changed=raw.replace('中','文')
    assert len(raw)==len(changed)
    with sqlite3.connect(path) as db:db.execute('UPDATE board SET payload=?',(changed,))
    second,new_version=read_cache.document(path,'board',ttl=0)
    assert second['rows']==['文'*10000] and new_version!=version and calls==[1]
