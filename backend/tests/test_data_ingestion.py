"""Ingestion test against the real akshare Sina-backed endpoint and a real Postgres DB."""
import pytest
from sqlalchemy import select

from app.models import Price, Ticker
from app.services import data_ingestion

pytestmark = pytest.mark.asyncio


async def test_ingest_then_reload_matches_row_count(db_session):
    count = await data_ingestion.ingest_ticker(db_session, "600519", "贵州茅台", start="20240101")
    assert count > 200  # roughly a year of trading days

    result = await db_session.execute(select(Ticker).where(Ticker.symbol == "600519"))
    ticker = result.scalar_one()
    assert ticker.last_synced_at is not None

    series = await data_ingestion.load_price_series(db_session, "600519")
    assert len(series) == count

    # re-ingesting the same window must upsert, not duplicate
    count2 = await data_ingestion.ingest_ticker(db_session, "600519", "贵州茅台", start="20240101")
    result = await db_session.execute(select(Price).where(Price.ticker_symbol == "600519"))
    assert len(result.scalars().all()) == count2
