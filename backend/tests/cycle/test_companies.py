"""公司识别不能把指数当股票、不能伪造分红或创建未知证券。"""
import httpx
import pytest
from app.cycle import companies


@pytest.mark.parametrize("value", ["600519", "600519.SH", "sh600519", "600519.SS"])
def test_same_security_code(value):
    assert companies.stock_code(value) == "600519"


@pytest.mark.parametrize("value", ["510300", "399006", "sh000001", "600519.SZ", "bad"])
def test_non_company_codes_rejected(value):
    with pytest.raises(ValueError):
        companies.stock_code(value)


def test_dividend_per_ten_and_no_future_records():
    def respond(req):
        assert 'SECURITY_CODE="600519"' in req.url.params["filter"]
        rows=[dict(SECURITY_CODE="600519",ASSIGN_PROGRESS="实施分配",EX_DIVIDEND_DATE="2026-06-01",PRETAX_BONUS_RMB=10,REPORT_DATE="2025-12-31"),dict(SECURITY_CODE="600519",ASSIGN_PROGRESS="实施分配",EX_DIVIDEND_DATE="2026-12-01",PRETAX_BONUS_RMB=99,REPORT_DATE="2026-06-30")]
        return httpx.Response(200,json={"success":True,"result":{"count":2,"data":rows}})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        d=companies.dividend_facts("600519","2026-11-06",100,client)
    assert d["cashPerShare"] == 1
    assert d["dividendYield"] == 1


def test_incomplete_dividend_data_not_published():
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={"success":True,"result":{"count":2,"data":[]}}))) as client:
        with pytest.raises(ValueError):
            companies.dividend_facts("600519","2026-11-06",100,client)


def test_unknown_security_is_not_created(monkeypatch):
    monkeypatch.setattr(companies,"fetch_quotes",lambda codes:{"quotes":[]})
    with pytest.raises(ValueError,match="未识别"):
        companies.identify("600519")


def test_identity_survives_optional_source_failure(monkeypatch):
    monkeypatch.setattr(companies,"fetch_quotes",lambda codes:{"quotes":[dict(code="600519",name="测试证券",price=100,quote_time="2026-11-06T15:00:00+08:00",symbol="sh600519")],"provider":"测试行情","fetched_at":"2026-11-07"})
    client=httpx.Client
    monkeypatch.setattr(companies.httpx,"Client",lambda **kw:client(transport=httpx.MockTransport(lambda req:httpx.Response(503))))
    data=companies.identify("600519")
    assert data["name"] == "测试证券"
    assert data["dividend"]["dividendYield"] is None
    assert data["quality"] is None
    assert data["industry"] is None
