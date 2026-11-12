from contextlib import contextmanager
import sqlite3
from datetime import datetime,timedelta
import pandas as pd
from app.cycle import trend_leader as t


def test_live_adapter_does_not_invent_missing_evidence(monkeypatch):
    now=datetime.now(t.TZ)
    dates=[(now.date()-timedelta(days=n)).isoformat() for n in range(100,0,-1)]
    frame=pd.DataFrame(dict(trade_date=dates,close=list(range(100,200))))
    monkeypatch.setattr(t,'fetch_daily',lambda *a,**kw:frame.copy())
    monkeypatch.setattr(t,'fetch_quotes',lambda *a:dict(provider='测试源',fetched_at=now.isoformat(),quotes=[dict(code='600519',name='测试',price=200,quote_time=now.isoformat())]))
    db=sqlite3.connect(':memory:')
    @contextmanager
    def store():
        yield db
    monkeypatch.setattr(t,'database',store)
    out=t.evaluate_live('600519')
    assert out['result']['decision']=='REJECT'
    assert 'sector.amount_share_history' in out['result']['missing_fields']
    assert out['source']['adjustment']=='不复权'
    assert db.execute('SELECT count(*) FROM trend_leader_audit').fetchone()[0]==1


def test_source_failure_does_not_fallback(monkeypatch):
    def fail(*a): raise ValueError('源不可用')
    monkeypatch.setattr(t,'fetch_quotes',fail)
    import pytest
    with pytest.raises(ValueError,match='源不可用'):t.evaluate_live('600519')
