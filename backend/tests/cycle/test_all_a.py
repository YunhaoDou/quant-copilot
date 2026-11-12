"""全A股范围完整性、非红利证券保留、切换记录可追溯。"""
import json
from contextlib import nullcontext
import httpx
import pytest
from app.cycle import all_a,events,experiment,strategy_center
from app.cycle.engine import load_config
from app.cycle.strategy_sim import new_account


def test_pages_collect_all_and_reject_short_page():
    def transport(request):
        page=int(request.url.params['pn'])
        rows=[{'f12':str(i)} for i in range((page-1)*100,min(page*100,251))]
        return httpx.Response(200,json={'data':{'total':251,'diff':rows}})
    with httpx.Client(transport=httpx.MockTransport(transport)) as c:
        rows=all_a.pages(c,'https://example.test',{'pz':100},'pn','market')
    assert len(rows)==251
    def missing(request):
        page=int(request.url.params['pn']);rows=[{}]*100 if page==1 else []
        return httpx.Response(200,json={'data':{'total':251,'diff':rows}})
    with httpx.Client(transport=httpx.MockTransport(missing)) as c:
        with pytest.raises(ValueError,match='未完整'):all_a.pages(c,'https://example.test',{'pz':100},'pn','market')


def test_all_a_does_not_require_dividends_or_truncate_to_100(tmp_path,monkeypatch):
    monkeypatch.setattr(events,'DB_PATH',tmp_path/'all-a.sqlite')
    monkeypatch.setattr(all_a.httpx,'Client',lambda **kw:nullcontext(object()))
    market=[dict(code=str(600000+i),name='合成样本',sector='电子',exchange='SH') for i in range(121)]
    monkeypatch.setattr(all_a,'official_master',lambda:market)
    monkeypatch.setattr(all_a,'pages',lambda *a:[])
    monkeypatch.setattr(all_a,'fetch_benchmark',lambda *a:None)
    p=all_a.refresh()
    assert p['total']==121 and len(p['stocks'])==121
    assert all(s['cashPerShare']==0 for s in p['stocks'])
    assert all_a.saved()['scope']=='all-a'


def test_value_financial_evidence_is_independent_of_dividend_qualification():
    stock={'name':'测试','quality':{'status':'unknown','financialEvidenceStatus':'supported','cashProfitRatio':1.2,'financialIndustry':False}}
    result=strategy_center.evaluate('quality-value',stock,{'price':10,'pe':10,'pb':1},{},None,load_config())
    assert result['status']=='pass'


def test_experiment_keeps_trades_and_backup_and_is_idempotent(tmp_path,monkeypatch):
    monkeypatch.setattr(events,'DB_PATH',tmp_path/'experiment.sqlite')
    with events.database() as db:
        strategy_center.schema(db);a=new_account(load_config());a['trades']=[{'price':10,'side':'buy'}]
        strategy_center.persist(db,'quality-value',a)
    first=experiment.setup();second=experiment.setup()
    assert first==second and first['start_date']=='2026-11-11'
    with events.database() as db:
        account=strategy_center.load(db,'quality-value')
        assert account['created_at']==a['created_at'] and account['trades'][0]['price']==10
        raw=db.execute('SELECT payload FROM strategy_scope_backup').fetchone()[0]
        assert 'universe_scope' not in json.loads(raw)['trades'][0]


def test_daily_scan_checkpoint_is_reused(tmp_path,monkeypatch):
    import pandas as pd
    from datetime import datetime,timedelta
    from app.cycle.live import TZ
    monkeypatch.setattr(events,'DB_PATH',tmp_path/'checkpoint.sqlite')
    today=datetime.now(TZ).date()
    snapshot={'scope':'all-a','tradeDate':today.isoformat(),'evidence_state':'财报与分红读取完成','stocks':[{'code':'600001'},{'code':'000001'}]}
    monkeypatch.setattr(all_a,'saved',lambda:snapshot)
    dates=pd.bdate_range(end=today-timedelta(days=1),periods=80)
    frame=pd.DataFrame({'trade_date':[d.date().isoformat() for d in dates],'close':list(range(100,180))})
    calls=[]
    def fetch(symbol,*args):calls.append(symbol);return frame.copy()
    monkeypatch.setattr(strategy_center,'fetch_daily',fetch)
    monkeypatch.setattr(strategy_center,'run_accounts',lambda:None)
    strategy_center.refresh_signals();strategy_center.refresh_signals()
    assert calls.count('600001')==1 and calls.count('000001')==1
    with events.database() as db:
        package=strategy_center.load(db,'quality-value','research_strategy_signals')
        assert package['scope']=='all-a' and package['checked']==2
