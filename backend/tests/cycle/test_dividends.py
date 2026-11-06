"""红利迁移规则的边界与真实分页完整性测试。"""
from datetime import date, timedelta

import httpx
import pytest

from app.cycle.dividends import build_dividends, classify, paginate, score
from app.cycle.engine import load_config


def record(ex, cash, progress="实施分配", **extra):
    return dict(SECURITY_CODE="600001",EX_DIVIDEND_DATE=ex,PRETAX_BONUS_RMB=cash,ASSIGN_PROGRESS=progress,REPORT_DATE=ex[:4]+"-06-30",**extra)


def test_cash_is_per_ten_shares_and_duplicates_removed():
    rows=[record("2026-06-01",10),record("2026-06-01",10),record("2026-10-01",5),record("2025-01-01",100),record("2026-12-01",20),record("2026-10-10",99,"董事会预案")]
    data=build_dividends(rows,"2026-11-06")["600001"]
    assert data["cashPerShare"] == 1.5
    assert data["consecutiveYears"] == 2
    assert all(r["exDate"] <= "2026-11-06" for r in data["dividendRecords"])


def test_dividend_year_gap_and_share_change():
    data=build_dividends([record("2026-01-01",10,BONUS_IT_RATIO=2),record("2024-01-01",10)],"2026-11-06")["600001"]
    assert data["consecutiveYears"] == 1
    assert data["shareChange"] is True


def test_score_and_classification():
    assert classify("股份制银行") == "金融"
    assert classify("煤炭开采") == "能源资源"
    assert 0 <= score(dict(history=[10]*120,dividendYield=6,lowPosition=20,consecutiveYears=8)) <= 100


def test_paginated_market_accepts_dict_and_rejects_incomplete():
    cfg={**load_config(),"dividend_workers":1}
    def respond(request):
        page=int(request.url.params["pn"])
        return httpx.Response(200,json={"data":{"total":3,"diff":{"0":{"f12":"a"},"1":{"f12":"b"}} if page == 1 else {"0":{"f12":"c"}}}})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        rows=paginate(client,"https://example.test",{},"pn",2,cfg,"market")
        assert len(rows)==3
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={"data":{"total":3,"diff":[]}}))) as client:
        with pytest.raises(ValueError,match="分页未完整"):
            paginate(client,"https://example.test",{},"pn",2,cfg,"market")
