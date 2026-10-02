"""Compliance Q&A tests. Retrieval runs against the REAL corpus in data/compliance/ (pure
TF-IDF cosine, no network, no LLM) so ranking correctness is genuinely verified — not just
that *some* chunk comes back, but that the *right* document tops the ranking for an
on-topic question. LLM calls are stubbed with a scripted FakeLLMClient."""
import json

import fakeredis.aioredis
import pytest

from app.services import compliance_qa
from app.services.compliance_qa import MAX_RETRIES, answer_question, retrieve


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


# ---- retrieval accuracy (real corpus, no mocking) ----

def test_day_trading_question_retrieves_pdt_doc_first():
    hits = retrieve("How many day trades before I'm flagged as a pattern day trader?")
    assert hits, "expected at least one hit"
    assert hits[0]["doc_id"] == "pdt_rule.md"


def test_naked_calls_question_retrieves_options_levels_doc_first():
    hits = retrieve("What options level do I need to sell uncovered naked calls?")
    assert hits, "expected at least one hit"
    assert hits[0]["doc_id"] == "options_approval_levels.md"


def test_reg_t_question_retrieves_margin_doc_first():
    hits = retrieve("What is the Regulation T initial margin requirement for buying stock?")
    assert hits, "expected at least one hit"
    assert hits[0]["doc_id"] == "reg_t_margin.md"


def test_suitability_question_retrieves_suitability_doc_first():
    hits = retrieve("Can I recommend a leveraged product to a conservative low-risk-tolerance customer?")
    assert hits, "expected at least one hit"
    assert hits[0]["doc_id"] == "suitability_rule_2111.md"


def test_unrelated_question_returns_no_hits():
    hits = retrieve("What's the weather forecast for Shanghai tomorrow?")
    assert hits == []


def test_finance_adjacent_but_unrelated_question_returns_no_hits():
    # Regression: "price"/"current" have weak lexical overlap with reg_t_margin.md's
    # "current market value"/"purchase price" language, which pushed this fully-unrelated
    # question over a too-low 0.05 similarity bar in live testing (grounded=True was wrong).
    hits = retrieve("What is the current price of Bitcoin?")
    assert hits == []


def test_naked_calls_question_without_word_uncovered_still_retrieves_options_doc():
    # Regression: per-heading chunking previously starved the "Level 4" subsection of the
    # doc's shared vocabulary, so dropping the exact word "uncovered" (very plausible
    # real phrasing) returned zero hits. Whole-document chunking fixed this.
    hits = retrieve("What options level do I need to sell naked calls?")
    assert hits and hits[0]["doc_id"] == "options_approval_levels.md"


def test_leveraged_etf_suitability_question_without_exact_wording_still_retrieves_doc():
    hits = retrieve("Can I recommend a leveraged ETF to a conservative retiree with low risk tolerance?")
    assert hits and hits[0]["doc_id"] == "suitability_rule_2111.md"


def test_scores_are_ordered_descending():
    hits = retrieve("margin requirement for short selling")
    scores = [h["score"] for h in hits]
    assert scores == sorted(scores, reverse=True)


# ---- answer orchestration ----

@pytest.mark.asyncio
async def test_ungrounded_question_skips_llm_entirely(redis):
    exhausted = FakeLLMClient([])
    result = await answer_question(redis, "What's the weather tomorrow?", client=exhausted)
    assert result["grounded"] is False
    assert result["citations"] == []
    assert exhausted.calls == 0


@pytest.mark.asyncio
async def test_grounded_question_calls_llm_and_returns_citations(redis):
    valid = json.dumps({
        "answer": "Pattern day traders must maintain $25,000 minimum equity.",
        "citations": ["pdt_rule.md"],
    })
    client = FakeLLMClient([valid])
    result = await answer_question(redis, "What is the PDT minimum equity requirement?", client=client)
    assert result["grounded"] is True
    assert result["citations"] == ["pdt_rule.md"]
    assert client.calls == 1


@pytest.mark.asyncio
async def test_hallucinated_citation_triggers_retry(redis):
    bogus = json.dumps({"answer": "x" * 20, "citations": ["made_up_doc.md"]})
    valid = json.dumps({"answer": "x" * 20, "citations": ["pdt_rule.md"]})
    client = FakeLLMClient([bogus, valid])
    result = await answer_question(redis, "What is the PDT minimum equity requirement?", client=client)
    assert client.calls == 2
    assert result["citations"] == ["pdt_rule.md"]


@pytest.mark.asyncio
async def test_raises_after_exhausting_retries(redis):
    always_bogus = json.dumps({"answer": "x" * 20, "citations": ["nope.md"]})
    client = FakeLLMClient([always_bogus] * (MAX_RETRIES + 1))
    with pytest.raises(ValueError, match="failed to produce a grounded"):
        await answer_question(redis, "What is the PDT minimum equity requirement?", client=client)


@pytest.mark.asyncio
async def test_second_call_hits_cache(redis):
    valid = json.dumps({"answer": "x" * 20, "citations": ["pdt_rule.md"]})
    client = FakeLLMClient([valid])
    await answer_question(redis, "What is the PDT minimum equity requirement?", client=client)

    exhausted = FakeLLMClient([])
    result2 = await answer_question(redis, "What is the PDT minimum equity requirement?", client=exhausted)
    assert result2["cache_hit"] is True
    assert exhausted.calls == 0


@pytest.mark.asyncio
async def test_different_lang_does_not_share_cache_entry(redis):
    en_client = FakeLLMClient([json.dumps({"answer": "x" * 20, "citations": ["pdt_rule.md"]})])
    await answer_question(redis, "What is the PDT minimum equity requirement?", client=en_client, lang="en")

    zh_client = FakeLLMClient([json.dumps({"answer": "x" * 20, "citations": ["pdt_rule.md"]})])
    result_zh = await answer_question(
        redis, "What is the PDT minimum equity requirement?", client=zh_client, lang="zh"
    )
    assert zh_client.calls == 1
    assert result_zh["cache_hit"] is False


def test_ungrounded_answer_message_is_localized():
    en = compliance_qa.NOT_COVERED_MESSAGE["en"]
    zh = compliance_qa.NOT_COVERED_MESSAGE["zh"]
    assert en != zh
    assert "合规" in zh


# ---- corpus sanity ----

def test_corpus_loaded_all_four_docs():
    doc_ids = {c.doc_id for c in compliance_qa._CHUNKS}
    assert doc_ids == {"pdt_rule.md", "reg_t_margin.md", "options_approval_levels.md", "suitability_rule_2111.md"}
