"""LLM-backed structured research notes: ticker -> thesis / catalysts / risks / fair value.

Also exposes the shared ``structured_completion`` helper used by every service that asks the
LLM for JSON: schema validation with automatic retry (the model is told exactly what broke
and asked to fix it) and Redis caching so a repeat request inside the TTL doesn't re-spend
tokens. Each caller keeps its own prompt text, cache key/TTL and transport.
"""
import json
from dataclasses import dataclass
from typing import Callable

import httpx
from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis

from app.config import settings
from app.schemas.research import ResearchNoteSchema
from app.services.i18n import DEFAULT_LANG, language_instruction

MODEL = settings.DEEPSEEK_MODEL
MAX_RETRIES = 2

SYSTEM_PROMPT = (
    "You are an equity research assistant. Given a ticker, produce a structured research "
    'note as a JSON object matching this schema: {"thesis": str, "catalysts": [str], '
    '"risks": [str], "fair_value_low": float, "fair_value_high": float}. '
    "Respond with ONLY the JSON object, no prose outside it."
)


class LLMClient:
    """DeepSeek (OpenAI-compatible) chat client. Tests inject a fake in its place, so the
    real network call lives only here and the orchestration stays provider-agnostic."""

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or settings.DEEPSEEK_API_KEY
        self._base_url = settings.DEEPSEEK_BASE_URL.rstrip("/")
        self._model = settings.DEEPSEEK_MODEL

    def complete(self, prompt: str, system_prompt: str | None = None) -> tuple[str, int, int]:
        if not self._api_key:
            raise ValueError("DEEPSEEK_API_KEY is not set — cannot call the LLM")
        resp = httpx.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
            json={
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system_prompt or SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.3,
                "max_tokens": 1024,
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return text, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)


@dataclass
class StructuredCompletion:
    """Outcome of one ``structured_completion`` call.

    ``payload`` is the caller-shaped dict that was cached (or read from cache); the retry and
    token counters let callers attach their own response metadata without the helper having to
    know each service's response shape.
    """

    payload: dict
    cache_hit: bool
    retries: int
    input_tokens: int
    output_tokens: int


async def read_cached_payload(
    redis: Redis, cache_key: str, *, cache_hit_fields: dict | None = None
) -> dict | None:
    """Redis-cache read shared by ``structured_completion`` and callers that need to short-circuit
    before doing any prep work (e.g. news_sentiment skips its headline fetch on a cache hit)."""
    cached = await redis.get(cache_key)
    if not cached:
        return None
    payload = json.loads(cached)
    payload["cache_hit"] = True
    if cache_hit_fields:
        payload.update(cache_hit_fields)
    return payload


async def structured_completion(
    redis: Redis,
    client: LLMClient | None,
    schema: type[BaseModel],
    prompt: str,
    *,
    cache_key: str,
    cache_ttl_hours: float,
    system_prompt: str,
    repair_prompt: Callable[[Exception], str],
    payload_from_model: Callable[[BaseModel], dict],
    error_message: str,
    validate_model: Callable[[BaseModel], None] | None = None,
    cache_hit_fields: dict | None = None,
    max_retries: int = MAX_RETRIES,
) -> StructuredCompletion:
    """Cache-or-call a JSON-mode LLM completion and validate it against ``schema``.

    On a cache hit the stored payload is returned untouched apart from ``cache_hit=True`` (plus
    ``cache_hit_fields``). On a miss the model is called up to ``max_retries + 1`` times: any JSON
    decode error, Pydantic validation error or caller ``validate_model`` error rebuilds the
    prompt through ``repair_prompt(exc)`` and retries; exhaustion raises ``ValueError`` with the
    caller's ``error_message``. ``payload_from_model`` builds the exact dict that is cached (so
    each caller keeps its response shape) before the helper adds ``cache_hit=False``.
    """
    cached = await read_cached_payload(redis, cache_key, cache_hit_fields=cache_hit_fields)
    if cached is not None:
        return StructuredCompletion(payload=cached, cache_hit=True, retries=0, input_tokens=0, output_tokens=0)

    client = client or LLMClient()
    current_prompt = prompt
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        text, input_tokens, output_tokens = client.complete(current_prompt, system_prompt=system_prompt)
        try:
            validated = schema.model_validate(json.loads(text))
            if validate_model is not None:
                validate_model(validated)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = exc
            current_prompt = repair_prompt(exc)
            continue

        payload = payload_from_model(validated)
        await redis.set(cache_key, json.dumps(payload), ex=cache_ttl_hours * 3600)
        payload["cache_hit"] = False
        return StructuredCompletion(
            payload=payload,
            cache_hit=False,
            retries=attempt,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    raise ValueError(f"{error_message} after {max_retries} retries: {last_error}")


def _cache_key(ticker: str, lang: str) -> str:
    return f"research_note:{ticker}:{lang}"


async def get_research_note(
    redis: Redis, ticker: str, client: LLMClient | None = None, lang: str = DEFAULT_LANG
) -> dict:
    """Returns a schema-validated research-note dict. Reads/writes the Redis cache."""
    mainland = ticker.upper().endswith((".SS", ".SZ", ".SH", ".BJ")) or ticker.isdigit()
    context = None
    if mainland and client is None:
        from app.cycle.market import fetch_quotes
        context = fetch_quotes([ticker])
        if not context["quotes"]:
            raise ValueError("未获取真实报价，无法生成有行情依据的研究笔记")
    cache_key = _cache_key(ticker, lang) + (":market-v1:" + context["quotes"][0]["quote_time"][:10] if context else "")
    system_prompt = SYSTEM_PROMPT + language_instruction(lang)
    prompt = f"Ticker: {ticker}\nProduce the research note JSON now."
    if context:
        prompt += "\n真实报价上下文：" + json.dumps(context, ensure_ascii=False) + "\n仅引用提供的已验证数字。缺少财务证据时明确说明待核实，估值只能作为假设，不得编造实时财报和消息。"

    def payload_from_model(validated: ResearchNoteSchema) -> dict:
        note = validated.model_dump()
        note["model"] = MODEL
        if context:
            note["market_context"] = context
        return note

    result = await structured_completion(
        redis,
        client,
        ResearchNoteSchema,
        prompt,
        cache_key=cache_key,
        cache_ttl_hours=settings.LLM_CACHE_TTL_HOURS,
        system_prompt=system_prompt,
        repair_prompt=lambda exc: (
            f"Ticker: {ticker}\nYour previous response failed schema validation: {exc}\n"
            "Return ONLY the corrected JSON object, nothing else."
        ),
        payload_from_model=payload_from_model,
        cache_hit_fields={"retries": 0, "input_tokens": 0, "output_tokens": 0},
        error_message="LLM failed to produce a schema-valid research note",
    )
    note = result.payload
    if not result.cache_hit:
        note.update(retries=result.retries, input_tokens=result.input_tokens, output_tokens=result.output_tokens)
    return note
