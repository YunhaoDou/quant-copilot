"""Verifies schema validation + auto-retry + Redis caching without calling the real
Anthropic API (no key is available in this environment). A FakeLLMClient stands in for
the network call so the orchestration logic — the actual thing this bullet claims — is
what's under test.
"""
import json

import fakeredis.aioredis
import pytest

from app.services.llm_research import MAX_RETRIES, get_research_note

pytestmark = pytest.mark.asyncio

VALID_NOTE = {
    "thesis": "Strong moat from brand pricing power and distribution network.",
    "catalysts": ["Volume growth in lower-tier cities", "Premiumization mix shift"],
    "risks": ["Regulatory pricing caps", "Slowing banquet/gifting demand"],
    "fair_value_low": 1500.0,
    "fair_value_high": 1900.0,
}


class FakeLLMClient:
    """Replays a scripted sequence of raw text responses, one per .complete() call."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls = 0

    def complete(self, prompt: str):
        self.calls += 1
        text = self._responses.pop(0)
        return text, 100, 50


@pytest.fixture
def redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


async def test_valid_response_on_first_try(redis):
    client = FakeLLMClient([json.dumps(VALID_NOTE)])
    note = await get_research_note(redis, "600519", client=client)

    assert note["thesis"] == VALID_NOTE["thesis"]
    assert note["retries"] == 0
    assert note["cache_hit"] is False
    assert client.calls == 1


async def test_retries_on_schema_violation_then_succeeds(redis):
    invalid = json.dumps({**VALID_NOTE, "fair_value_high": 100.0})  # high < low -> invalid
    client = FakeLLMClient([invalid, json.dumps(VALID_NOTE)])

    note = await get_research_note(redis, "600519", client=client)

    assert client.calls == 2
    assert note["retries"] == 1
    assert note["fair_value_high"] == VALID_NOTE["fair_value_high"]


async def test_retries_on_malformed_json_then_succeeds(redis):
    client = FakeLLMClient(["not json at all", json.dumps(VALID_NOTE)])
    note = await get_research_note(redis, "600519", client=client)
    assert client.calls == 2
    assert note["thesis"] == VALID_NOTE["thesis"]


async def test_raises_after_exhausting_retries(redis):
    always_broken = ["still not json"] * (MAX_RETRIES + 1)
    client = FakeLLMClient(always_broken)

    with pytest.raises(ValueError, match="failed to produce a schema-valid"):
        await get_research_note(redis, "600519", client=client)
    assert client.calls == MAX_RETRIES + 1


async def test_second_call_hits_cache_and_skips_llm(redis):
    client = FakeLLMClient([json.dumps(VALID_NOTE)])
    await get_research_note(redis, "600519", client=client)

    # second call must not touch the client at all
    exhausted_client = FakeLLMClient([])
    note2 = await get_research_note(redis, "600519", client=exhausted_client)

    assert note2["cache_hit"] is True
    assert exhausted_client.calls == 0
