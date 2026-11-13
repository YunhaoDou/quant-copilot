"""全A股深入核验不截断，失败证券也保留；测试数据只写临时数据库。"""
from datetime import datetime,timedelta
import pandas as pd
from app.cycle import events,all_a,full_market
from app.cycle.live import TZ


def test_every_stock_including_beyond_320_and_missing_is_retained(tmp_path,monkeypatch):
    monkeypatch.setattr(events,'DB_PATH',tmp_path/'full.sqlite')
    now=datetime.now(TZ)
    stocks=[dict(code=str(600000+i),name=f'合成样本{i}',sector='电子',category='科技通信',cashPerShare=0,consecutiveYears=0,historicalCashPerShare=None,quality={'status':'unknown','financialIndustry':False,'historicalYield':None}) for i in range(321)]
    master=dict(stocks=stocks,total=len(stocks),tradeDate=now.date().isoformat(),schema_version=2,source='合成测试源')
    monkeypatch.setattr(all_a,'saved',lambda:master)
    def quotes(codes):return {'quotes':[dict(code=code,name=code,price=10,quote_time=now.isoformat()) for code in codes]}
    monkeypatch.setattr(full_market,'fetch_quotes',quotes)
    dates=pd.bdate_range(end=now.date()-timedelta(days=1),periods=320)
    frame=pd.DataFrame(dict(trade_date=[d.date().isoformat() for d in dates],open=10.,high=11.,low=9.,close=10.,volume=1000.))
    calls=[]
    def daily(code,count):
        calls.append(code)
        if code=='600002':raise ValueError('测试缺失')
        return frame.copy()
    monkeypatch.setattr(full_market,'fetch_daily',daily)
    p=full_market.scan(lambda **kw:None)
    assert p['scanned']==321 and p['checked']==321 and len(p['stocks'])==321
    assert {s['code'] for s in p['stocks']}=={s['code'] for s in stocks}
    missing=next(s for s in p['stocks'] if s['code']=='600002')
    assert missing['lowPosition'] is None and missing['dataErrors']
    assert any(s['code']=='600320' for s in p['stocks'])
    rank=full_market.screening_snapshot()
    assert len(rank['results'])==321 and rank['unknown']==1
    assert next(s for s in rank['results'] if s['symbol']=='600002')['composite_score'] is None
    full_market.scan(lambda **kw:None)
    assert calls.count('600320')==1
    assert calls.count('600002')==2
