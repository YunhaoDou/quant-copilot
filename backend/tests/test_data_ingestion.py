"""Ingestion test against the real yfinance endpoint and a real Postgres DB (US equities)."""
import pytest
from sqlalchemy import select

from app.models import Price, Ticker
from app.services import data_ingestion

pytestmark = pytest.mark.asyncio


async def test_ingest_then_reload_matches_row_count(db_session):
    count = await data_ingestion.ingest_ticker(db_session, "AAPL", "Apple Inc.", start="20240101")
    assert count > 200  # roughly a year of trading days

    result = await db_session.execute(select(Ticker).where(Ticker.symbol == "AAPL"))
    ticker = result.scalar_one()
    assert ticker.last_synced_at is not None
    assert ticker.market == "US"

    series = await data_ingestion.load_price_series(db_session, "AAPL")
    assert len(series) == count

    # re-ingesting the same window must upsert, not duplicate
    count2 = await data_ingestion.ingest_ticker(db_session, "AAPL", "Apple Inc.", start="20240101")
    result = await db_session.execute(select(Price).where(Price.ticker_symbol == "AAPL"))
    assert len(result.scalars().all()) == count2
