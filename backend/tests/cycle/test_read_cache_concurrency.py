"""冷缓存任务不能阻塞无关查询，且并发不能破坏版本和显式失效。"""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4
import json
import sqlite3
from starlette.requests import Request
from app.cycle import read_cache


def test_model_build_does_not_block_other_kind_or_encoded_response():
    started=Event();release=Event();kind=uuid4().hex
    def slow():started.set();release.wait(3);return {"rows":[1,2]}
    with ThreadPoolExecutor(3) as pool:
        first=pool.submit(read_cache.model,kind,"v1",slow)
        try:
            assert started.wait(1)
            other=pool.submit(read_cache.model,kind+"other","v1",lambda:{"rows":[3]})
            assert other.result(timeout=.5)["rows"]==[3]
            result=pool.submit(read_cache.response,{"ok":True},Request({"type":"http","headers":[]}))
            assert result.result(timeout=.5).status_code==200
        finally:release.set()
        assert first.result()["rows"]==[1,2]


def test_same_kind_and_version_builds_once_and_keeps_three_versions():
    calls=[];kind=uuid4().hex;started=Event();release=Event()
    def build():calls.append(1);started.set();release.wait(3);return {"rows":[1]}
    with ThreadPoolExecutor(2) as pool:
        first=pool.submit(read_cache.model,kind,"one",build);assert started.wait(1)
        second=pool.submit(read_cache.model,kind,"one",build);release.set()
        a,b=first.result(),second.result()
    assert a is b and calls==[1]
    for key in ['two','three','four']:current=read_cache.model(kind,key,lambda:{"rows":[]})
    assert len(read_cache._models[kind])==3
    from fastapi import HTTPException
    try:read_cache.versioned(kind,current,a['snapshot_version'])
    except HTTPException as exc:assert exc.status_code==409
    else:raise AssertionError('过期版本不可拼接')


def test_explicit_invalidation_during_decode_cannot_restore_old_document(tmp_path,monkeypatch):
    path=tmp_path/'data.sqlite';old=json.dumps({'value':'old'});new=json.dumps({'value':'new'})
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE board(id INTEGER PRIMARY KEY,payload TEXT)');db.execute('INSERT INTO board VALUES(1,?)',(old,))
    started=Event();release=Event();loads=json.loads
    def blocked(raw,*args,**kwargs):
        if raw==old:started.set();release.wait(3)
        return loads(raw,*args,**kwargs)
    monkeypatch.setattr(read_cache.json,'loads',blocked)
    with ThreadPoolExecutor(1) as pool:
        first=pool.submit(read_cache.document,path,'board')
        try:
            assert started.wait(1);read_cache.invalidate_documents()
            with sqlite3.connect(path) as db:db.execute('UPDATE board SET payload=?',(new,))
        finally:release.set()
        assert first.result()[0]['value']=='old'
    assert read_cache.document(path,'board')[0]['value']=='new'
