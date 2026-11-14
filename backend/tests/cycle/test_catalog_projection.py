"""只读策略总览投影不能改变展示字段、独立详情或持久化账本。"""
import copy
import json
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.cycle import events,strategy_center,read_api,trend_forward,shibor_sim,experiment


def test_overview_projection_matches_full_catalog_and_preserves_ledger(tmp_path,monkeypatch):
    monkeypatch.setattr(events,'DB_PATH',tmp_path/'events.sqlite')
    monkeypatch.setattr(trend_forward,'status',lambda:{'account':None})
    monkeypatch.setattr(shibor_sim,'status',lambda:{'account':None})
    monkeypatch.setattr(experiment,'setup',lambda:{'start_date':'2026-11-13'})
    account={'status':'running','capital':100000,'cash':50000,'equity':100001,'peak':100002,'created_at':'t',
             'position':{'symbol':'600000','quantity':100,'mark':3},'positions':{},'pending':None,'rules':{'lot_size':100},
             'processed':{'large':['processed']*10000},'candidates':[{'code':'600000'}],
             'data':{'generated_at':'t','failures':['missing'],'pool_total':5580,'checked':5},
             'trades':[{'price':3}],'decisions':[{'text':'test'}],'curve':[{'equity':100001}],'completed_legs':[]}
    with events.database() as db:
        strategy_center.schema(db)
        for spec in strategy_center.RESEARCH_CATALOG:strategy_center.persist(db,spec['id'],account)
    full=strategy_center.catalog()
    app=FastAPI();app.include_router(read_api.router);client=TestClient(app)
    keep={'status','capital','cash','equity','peak','created_at','position','positions','pending','rules'}
    for detail in [None,*[s['id'] for s in strategy_center.CATALOG]]:
        expected=copy.deepcopy(full['strategies'])
        for spec in expected:
            a=spec.get('account')
            if a is not None:
                spec['account']={k:v for k,v in a.items() if k!='candidates'} if spec['id']==detail and detail not in ('leader-rebound','trend-leader-band','shibor-rotation') else {k:v for k,v in a.items() if k in keep}
                # processed为既有详情接口保留字段，即使前端不展示也不可删。
        response=client.get('/strategy-center/overview',params={'detail_id':detail} if detail else {})
        assert response.status_code==200
        assert response.json()['strategies']==expected
    with events.database() as db:
        for spec in strategy_center.RESEARCH_CATALOG:assert strategy_center.load(db,spec['id'])==account
