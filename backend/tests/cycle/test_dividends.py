"""红利迁移规则的边界与真实分页完整性测试。"""
from datetime import date, timedelta

import httpx
import pytest

from app.cycle.dividends import build_dividends, classify, paginate
from app.cycle.dividend_quality import annual_statements, assess_quality, quality_order
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


def test_classification():
    assert classify("股份制银行") == "金融"
    assert classify("煤炭开采") == "能源资源"


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


def test_historical_median_and_fiscal_payout_use_separate_years():
    rows = [
        record("2023-06-01", 10, TOTAL_SHARES=1000),
        record("2024-06-01", 20, TOTAL_SHARES=1000),
        {**record("2025-06-01", 30, TOTAL_SHARES=1000), "REPORT_DATE": "2024-09-30"},
        {**record("2025-12-01", 10, TOTAL_SHARES=1000), "REPORT_DATE": "2025-09-30"},
        {**record("2026-06-01", 40, TOTAL_SHARES=1000), "REPORT_DATE": "2025-12-31"},
    ]
    item = build_dividends(rows, "2026-11-06")["600001"]
    assert item["historicalCashPerShare"] == 2
    assert item["cashPerShare"] == 5
    assert item["fiscalDistributions"] == {2025: 5000}
    rows[-1]["TOTAL_SHARES"] = None
    assert build_dividends(rows, "2026-11-06")["600001"]["fiscalDistributions"] == {}


def statements():
    return {
        "income": {("600001", y): {"PARENT_NETPROFIT": 1000, "DEDUCT_PARENT_NETPROFIT": 900} for y in range(2023, 2026)},
        "cash": {("600001", 2025): {"NETCASH_OPERATE": 850, "CONSTRUCT_LONG_ASSET": 200}},
        "balance": {("600001", 2025): {"TOTAL_ASSETS": 1000, "TOTAL_LIABILITIES": 350}},
    }


def test_quality_separates_cash_backed_risky_missing_and_financial():
    config = load_config()
    stock = dict(code="600001", category="工业材料", cashPerShare=3, price=50, historicalCashPerShare=2,
                 fiscalDistributions={2025: 500}, consecutiveYears=5, dividendYield=6)
    supported = assess_quality(stock, statements(), config)
    assert supported["status"] == "supported"
    assert supported["payoutPct"] == 50
    assert supported["fcfCover"] == pytest.approx(1.3)
    assert supported["historicalYield"] == 4
    risk = assess_quality({**stock, "fiscalDistributions": {2025: 1100}}, statements(), config)
    assert risk["status"] == "risk"
    assert quality_order({**stock, "quality": supported}) < quality_order({**stock, "quality": risk, "dividendYield": 20})
    missing = assess_quality(stock, {**statements(), "cash": {}}, config)
    assert missing["status"] == "unknown"
    assert missing["fcfCover"] is None
    financial = assess_quality({**stock, "category": "金融"}, statements(), config)
    assert financial["status"] == "financial"
    assert financial["fcfCover"] is None and financial["debtPct"] is None
    spiked = assess_quality({**stock, "cashPerShare": 4}, statements(), config)
    assert spiked["status"] == "review" and spiked["flags"]


def test_financial_batches_never_read_after_as_of_and_flag_partial_response():
    def respond(request):
        name = request.url.params["reportName"]
        rows = [
            {"SECURITY_CODE": "600001", "REPORT_DATE": "2025-12-31", "NOTICE_DATE": "2026-04-18"},
            {"SECURITY_CODE": "600001", "REPORT_DATE": "2024-12-31", "NOTICE_DATE": "2025-04-18"},
        ]
        return httpx.Response(200, json={"success": True, "result": {"count": 3 if name.endswith("BALANCE") else 2, "data": rows}})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        data, errors = annual_statements(client, ["600001"], "2026-04-17", load_config())
    assert set(data["income"]) == {("600001", 2024)}
    assert data["balance"] == {}
    assert len(errors) == 1
