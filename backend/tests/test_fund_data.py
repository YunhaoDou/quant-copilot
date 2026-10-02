"""Fund ingestion tests against the real AKShare endpoints and a real Postgres DB
(matches this project's convention of testing against real data, not mocks — see
test_data_ingestion.py). Covers both fund shapes: on-exchange ETF and OTC open-end.
"""
import pytest
from sqlalchemy import select

from app.models import Fund, FundNav
from app.services import fund_data

def test_detect_fund_type():
    assert fund_data.detect_fund_type("513330") == "ETF"  # 恒生科技 ETF, on-exchange
    assert fund_data.detect_fund_type("160119") == "LOF"
    assert fund_data.detect_fund_type("011452") == "OTC"


@pytest.mark.asyncio
async def test_ingest_etf_then_reload_matches_row_count(db_session):
    count = await fund_data.ingest_fund(db_session, "513330", start="20240101")
    assert count > 100

    fund = (await db_session.execute(select(Fund).where(Fund.code == "513330"))).scalar_one()
    assert fund.fund_type == "ETF"
    assert fund.last_synced_at is not None

    series = await fund_data.load_nav_series(db_session, "513330")
    assert len(series) == count

    # re-ingesting the same window must upsert, not duplicate
    count2 = await fund_data.ingest_fund(db_session, "513330", start="20240101")
    rows = (await db_session.execute(select(FundNav).where(FundNav.fund_code == "513330"))).scalars().all()
    assert len(rows) == count2


@pytest.mark.asyncio
async def test_ingest_otc_fund_populates_nav_and_acc_nav(db_session):
    count = await fund_data.ingest_fund(db_session, "011452", start="20240101")
    assert count > 0

    fund = (await db_session.execute(select(Fund).where(Fund.code == "011452"))).scalar_one()
    assert fund.fund_type == "OTC"

    rows = (
        (await db_session.execute(select(FundNav).where(FundNav.fund_code == "011452")))
        .scalars()
        .all()
    )
    assert any(r.nav is not None for r in rows)
    assert all(r.close is None for r in rows)  # OTC funds have no on-exchange price
