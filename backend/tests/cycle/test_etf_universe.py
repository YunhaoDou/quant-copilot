"""全ETF名册与扫描覆盖边界，不使用外网。"""
from datetime import datetime
import json
import pandas as pd
from app.cycle import etf_universe as e,events
from app.cycle.live import TZ


def test_full_etf_scan_keeps_missing_and_beyond_old_caps(tmp_path,monkeypatch):
    monkeypatch.setattr(events,"DB_PATH",tmp_path/"etfs.sqlite")
    rows=[dict(code=str(510000+i),name=f"ETF{i}",exchange="SH",asset_type="ETF",category="股票") for i in range(321)]
    monkeypatch.setattr(e,"official_etfs",lambda:rows)
    now=datetime.now(TZ)
    monkeypatch.setattr(e,"fetch_quotes",lambda codes:{"quotes":[dict(code=c,price=1.,quote_time=now.isoformat(),pe=100,pb=1) for c in codes if c!="510002"]})
    def daily(code,count):
        if code=="510003":raise ValueError("缺失")
        return pd.DataFrame(dict(trade_date=pd.bdate_range(end=now.date(),periods=300).strftime("%Y-%m-%d"),close=[1+i*.001 for i in range(300)]))
    monkeypatch.setattr(e,"fetch_daily",daily);e.refresh();p=e.saved()
    assert p["total"]==p["checked"]==321 and len(p["rows"])==321
    assert next(r for r in p["rows"] if r["code"]=="510002")["status"]=="unknown"
    assert next(r for r in p["rows"] if r["code"]=="510003")["status"]=="unknown"
    assert p["rows"][-1]["code"]=="510320" and p["rows"][-1]["quote"]["pe"] is None
    assert e.listing(page=7,page_size=50,query="",category="全部")["rows"][-1]["code"]=="510320"
    assert e.is_etf("510320") and not e.is_etf("600519")


def test_short_etf_history_preserves_unknown_metrics():
    f=pd.DataFrame(dict(trade_date=["2026-11-11","2026-11-12"],close=[1.,1.01]))
    m=e.history_metrics(f)
    assert m["return20"] is None and m["ma200"] is None and m["history_count"]==2
