"""轻量名单搜索必须覆盖全部证券，并与原名单代码、名称、顺序一致。"""
import copy
import json
import sqlite3
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.cycle import events,read_cache,security_search


@pytest.fixture
def fixture(tmp_path,monkeypatch):
    path=tmp_path/'universe.sqlite';monkeypatch.setattr(events,'DB_PATH',path)
    stocks=[{'code':str(600000+i),'name':f'公司{i}','exchange':'SH'} for i in range(321)]
    stocks.append({'code':'920001','name':'北交所公司','exchange':'BJ'})
    etfs=[{'code':str(159900+i),'name':f'ETF{i}','exchange':'SZ'} for i in range(45)]
    with sqlite3.connect(path) as db:
        for table,rows,key in [('all_a_universe',stocks,'stocks'),('etf_universe',etfs,'rows')]:
            db.execute(f'CREATE TABLE {table}(id INTEGER PRIMARY KEY,payload TEXT)');db.execute(f'INSERT INTO {table} VALUES(1,?)',(json.dumps({key:rows,'source':'官方名单测试夹具'}),))
    app=FastAPI();app.include_router(security_search.router);client=TestClient(app)
    return client,path,stocks,etfs


def test_all_pages_keep_full_universe_order_and_off_page_selection(fixture):
    client,_,stocks,etfs=fixture;first=client.get('/tickers/search',params={'selected':'600320.SS'}).json()
    assert first['selected']['code']=='600320' and first['total']==367 and first['stock_total']==322 and first['etf_total']==45
    rows=[]
    for page in range(1,9):rows+=client.get('/tickers/search',params={'page':page,'version':first['snapshot_version']}).json()['rows']
    assert [r['code'] for r in rows]==[r['code'] for r in stocks+etfs]
    assert [r['name'] for r in rows]==[r['name'] for r in stocks+etfs]
    assert len({r['symbol'] for r in rows})==367 and next(r['symbol'] for r in rows if r['code']=='920001')=='920001.BJ'
    assert len(client.get('/tickers/search').content)<15000


def test_full_market_query_types_and_exchange_qualification(fixture):
    client,*_=fixture
    for query in ['600320','600320.SH','600320.SS','sh600320','公司320']:
        data=client.get('/tickers/search',params={'query':query}).json();assert data['matched']==1 and data['rows'][0]['code']=='600320'
    assert client.get('/tickers/search',params={'query':'sz600320'}).json()['matched']==0
    assert client.get('/tickers/search',params={'asset_type':'ETF'}).json()['matched']==45
    assert client.get('/tickers/search',params={'query':'920001'}).json()['rows'][0]['exchange']=='BJ'
    assert client.get('/tickers/search',params={'asset_type':'other'}).status_code==422
    assert client.get('/tickers/search',params={'page_size':10000}).status_code==422


def test_versions_and_etag_keep_paging_consistent(fixture):
    client,path,stocks,etfs=fixture;before=client.get('/tickers/search');version=before.json()['snapshot_version']
    assert client.get('/tickers/search',headers={'If-None-Match':before.headers['etag']}).status_code==304
    changed=copy.deepcopy(stocks);changed[0]['name']='更新后的名称'
    with sqlite3.connect(path) as db:db.execute('UPDATE all_a_universe SET payload=?',(json.dumps({'stocks':changed}),))
    read_cache.invalidate_documents()
    assert client.get('/tickers/search').json()['rows'][0]['name']=='更新后的名称'
    assert client.get('/tickers/search',params={'version':version}).json()['rows'][0]['name']=='公司0'
    assert client.get('/tickers/search',params={'version':'expired'}).status_code==409


def test_missing_etf_source_is_explicit_unknown_not_zero(fixture):
    client,path,*_=fixture
    with sqlite3.connect(path) as db:db.execute('DELETE FROM etf_universe')
    read_cache.invalidate_documents();data=client.get('/tickers/search').json()
    assert data['etf_total'] is None and data['notes'] and data['total']==322
