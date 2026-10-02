"""News-sentiment tests. yfinance's news fetch is monkeypatched (no network) and the LLM
call is replaced by a scripted FakeLLMClient, so classification/aggregation/caching logic
is what's actually under test."""
import json

import fakeredis.aioredis
import pytest

from app.services import news_sentiment
from app.services.news_sentiment import MAX_RETRIES, get_news_sentiment

pytestmark = pytest.mark.asyncio

HEADLINES = [
    {"title": "Company beats earnings, raises guidance", "summary": "", "published_at": "2026-07-20T00:00:00Z", "publisher": "Yahoo Finance", "url": "https://example.com/1"},
    {"title": "Analyst maintains hold rating", "summary": "", "published_at": "2026-07-20T00:00:00Z", "publisher": "Yahoo Finance", "url": "https://example.com/2"},
]

VALID_CLASSIFICATION = {
    "items": [
        {"index": 0, "impact": "high", "reason": "Earnings beat moves the stock"},
        {"index": 1, "impact": "low", "reason": "Routine analyst maintenance"},
    ]
}


class FakeLLMClient:
    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls = 0

    def complete(self, prompt: str, system_prompt: str | None = None):
        self.calls += 1
        return self._responses.pop(0), 100, 50


@pytest.fixture
def redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture(autouse=True)
def patch_headlines(monkeypatch):
    monkeypatch.setattr(news_sentiment, "_fetch_headlines", lambda symbol: HEADLINES)


async def test_classifies_each_headline_and_aggregates(redis):
    client = FakeLLMClient([json.dumps(VALID_CLASSIFICATION)])
    result = await get_news_sentiment(redis, "AAPL", client=client)

    assert result["symbol"] == "AAPL"
    assert len(result["items"]) == 2
    assert result["items"][0]["impact"] == "high"
    assert result["items"][1]["impact"] == "low"
    # weighted avg: (3 + 1) / 2 = 2.0 -> "medium" band (>=1.5, <2.5)
    assert result["avg_impact_score"] == 2.0
    assert result["overall_signal"] == "medium"
    assert result["high_impact_count"] == 1
    assert client.calls == 1


async def test_retries_when_classification_count_mismatches(redis):
    too_few = json.dumps({"items": [{"index": 0, "impact": "high", "reason": "x"}]})
    client = FakeLLMClient([too_few, json.dumps(VALID_CLASSIFICATION)])

    result = await get_news_sentiment(redis, "AAPL", client=client)
    assert client.calls == 2
    assert len(result["items"]) == 2


async def test_raises_after_exhausting_retries(redis):
    always_broken = ["not json"] * (MAX_RETRIES + 1)
    client = FakeLLMClient(always_broken)
    with pytest.raises(ValueError, match="failed to produce schema-valid"):
        await get_news_sentiment(redis, "AAPL", client=client)


async def test_second_call_hits_cache(redis):
    client = FakeLLMClient([json.dumps(VALID_CLASSIFICATION)])
    await get_news_sentiment(redis, "AAPL", client=client)

    exhausted = FakeLLMClient([])
    result2 = await get_news_sentiment(redis, "AAPL", client=exhausted)
    assert result2["cache_hit"] is True
    assert exhausted.calls == 0


async def test_different_lang_does_not_share_cache_entry(redis):
    en_client = FakeLLMClient([json.dumps(VALID_CLASSIFICATION)])
    await get_news_sentiment(redis, "AAPL", client=en_client, lang="en")

    zh_client = FakeLLMClient([json.dumps(VALID_CLASSIFICATION)])
    result_zh = await get_news_sentiment(redis, "AAPL", client=zh_client, lang="zh")

    assert zh_client.calls == 1
    assert result_zh["cache_hit"] is False


async def test_no_headlines_returns_quiet_signal_without_calling_llm(redis, monkeypatch):
    monkeypatch.setattr(news_sentiment, "_fetch_headlines", lambda symbol: [])
    exhausted = FakeLLMClient([])
    result = await get_news_sentiment(redis, "ZZZ", client=exhausted)
    assert result["overall_signal"] == "quiet"
    assert result["items"] == []
    assert exhausted.calls == 0
