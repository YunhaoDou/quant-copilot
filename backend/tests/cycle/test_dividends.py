"""红利迁移规则的边界与真实分页完整性测试。"""
from datetime import date

import httpx
import pytest

from app.cycle.dividends import build_dividends, classify
from app.cycle.dividend_benchmark import fetch_benchmark, parse_benchmark
from app.cycle.dividend_quality import assess_quality, quality_order, screen_candidate
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
    assert supported["ocfCover"] == pytest.approx(1.7)
    assert supported["cashProfitRatio"] == pytest.approx(0.85)
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


def test_bond_curve_uses_published_prior_date_and_rejects_changed_layout():
    def row(day, rate, other="", label="中债国债收益率曲线"):
        return "<tr>" + "".join(f"<td>{value}</td>" for value in [label, day, other, "", "", "", "", "", rate, ""]) + "</tr>"

    html = row("2026-11-09", 2.2) + row("2026-11-06", 1.6) + row("2026-10-16", 1.7)
    def response(request):
        assert request.url.params["endDate"] == "2026-11-08"
        assert request.url.params["gjqx"] == "10"
        return httpx.Response(200, text=html)

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        assert fetch_benchmark(client, "2026-11-09") == {
            "date": "2026-11-06", "yieldPct": 1.6, "previousDate": "2026-10-16", "changeBp": -10,
        }
    with pytest.raises(ValueError, match="未返回"):
        parse_benchmark(row("2026-11-06", 1.6, other="1.0"), date(2026, 11, 8))


def test_automatic_screen_reports_thresholds_and_keeps_uncertainty():
    config = load_config()
    stock = {
        "dividendYield": 4, "consecutiveYears": 5,
        "quality": {"status": "supported", "historicalYield": 3.5, "payoutPct": 70,
                    "ocfCover": 1.5, "cashProfitRatio": .8, "fcfCover": 1},
    }
    benchmark = {"yieldPct": 1.5}
    result = screen_candidate(stock, benchmark, config)
    assert result["status"] == "pass"
    assert len(result["checks"]) == 7 and all(item["passed"] for item in result["checks"])
    assert screen_candidate(stock, None, config)["status"] == "unknown"
    assert screen_candidate({**stock, "dividendYield": 6.01}, benchmark, config)["status"] == "fail"
    assert screen_candidate({**stock, "quality": {**stock["quality"], "status": "risk"}}, benchmark, config)["status"] == "fail"
    assert screen_candidate({**stock, "quality": {**stock["quality"], "financialIndustry": True}}, benchmark, config)["status"] == "manual"
