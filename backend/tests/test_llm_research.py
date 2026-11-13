"""Verifies schema validation + auto-retry + Redis caching without calling the real
Anthropic API (no key is available in this environment). A FakeLLMClient stands in for
the network call so the orchestration logic — the actual thing this bullet claims — is
what's under test. The shared structured_completion helper (also used by news_sentiment
and compliance_qa) gets its own contract tests here.
"""
import json

import fakeredis.aioredis
import pytest
from pydantic import BaseModel, Field

from app.services.llm_research import MAX_RETRIES, get_research_note, structured_completion

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

    def complete(self, prompt: str, system_prompt: str | None = None):
        self.calls += 1
        text = self._responses.pop(0)
        return text, 100, 50


@pytest.fixture
def redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


# ---- shared structured_completion helper contract (used by llm_research/news/compliance) ----

class TinySchema(BaseModel):
    answer: str = Field(min_length=3)


class RecordingFakeLLMClient(FakeLLMClient):
    def __init__(self, responses: list[str]):
        super().__init__(responses)
        self.prompts: list[str] = []

    def complete(self, prompt: str, system_prompt: str | None = None):
        self.prompts.append(prompt)
        return super().complete(prompt, system_prompt)


async def test_structured_completion_retries_with_caller_repair_prompt_then_caches(redis):
    client = RecordingFakeLLMClient(['{"answer": ""}', json.dumps({"answer": "fixed"})])

    result = await structured_completion(
        redis,
        client,
        TinySchema,
        "initial prompt",
        cache_key="toy:1",
        cache_ttl_hours=1,
        system_prompt="toy system prompt",
        repair_prompt=lambda exc: f"repair:{exc}",
        payload_from_model=lambda validated: {"answer": validated.answer},
        error_message="toy helper failed",
    )

    assert client.calls == 2
    assert client.prompts[0] == "initial prompt"
    assert client.prompts[1].startswith("repair:")
    assert result.cache_hit is False and result.retries == 1
    assert result.payload == {"answer": "fixed", "cache_hit": False}
    # The caller-shaped payload (not the validated model) is what lands in Redis.
    assert json.loads(await redis.get("toy:1")) == {"answer": "fixed"}

    exhausted = RecordingFakeLLMClient([])
    cached = await structured_completion(
        redis,
        exhausted,
        TinySchema,
        "initial prompt",
        cache_key="toy:1",
        cache_ttl_hours=1,
        system_prompt="toy system prompt",
        repair_prompt=lambda exc: f"repair:{exc}",
        payload_from_model=lambda validated: {"answer": validated.answer},
        error_message="toy helper failed",
        cache_hit_fields={"retries": 0},
    )
    assert exhausted.calls == 0
    assert cached.cache_hit is True and cached.retries == 0
    assert cached.payload == {"answer": "fixed", "cache_hit": True, "retries": 0}


async def test_structured_completion_raises_callers_error_message_after_retries(redis):
    client = RecordingFakeLLMClient(["still not json"] * (MAX_RETRIES + 1))
    with pytest.raises(ValueError, match="toy helper failed after 2 retries"):
        await structured_completion(
            redis,
            client,
            TinySchema,
            "initial prompt",
            cache_key="toy:2",
            cache_ttl_hours=1,
            system_prompt="toy system prompt",
            repair_prompt=lambda exc: f"repair:{exc}",
            payload_from_model=lambda validated: {"answer": validated.answer},
            error_message="toy helper failed",
        )
    assert client.calls == MAX_RETRIES + 1


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


async def test_different_lang_does_not_share_cache_entry(redis):
    # Regression: en/zh must not collide on the same Redis key, or a Chinese request
    # would silently be served a cached English note (or vice versa).
    en_client = FakeLLMClient([json.dumps(VALID_NOTE)])
    await get_research_note(redis, "600519", client=en_client, lang="en")

    zh_client = FakeLLMClient([json.dumps(VALID_NOTE)])
    note_zh = await get_research_note(redis, "600519", client=zh_client, lang="zh")

    assert zh_client.calls == 1  # not served from the "en" cache entry
    assert note_zh["cache_hit"] is False
