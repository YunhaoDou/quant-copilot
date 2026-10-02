"""LLM-backed structured research notes: ticker -> thesis / catalysts / risks / fair value.

Schema-validated with automatic retry on validation failure (the model is told exactly
what broke and asked to fix it), and Redis-cached per ticker for LLM_CACHE_TTL_HOURS so a
repeat request within the window doesn't re-spend tokens.
"""
import json

import httpx
from pydantic import ValidationError
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


def _cache_key(ticker: str, lang: str) -> str:
    return f"research_note:{ticker}:{lang}"


async def get_research_note(
    redis: Redis, ticker: str, client: LLMClient | None = None, lang: str = DEFAULT_LANG
) -> dict:
    """Returns a schema-validated research-note dict. Reads/writes the Redis cache."""
    cached = await redis.get(_cache_key(ticker, lang))
    if cached:
        note = json.loads(cached)
        note.update(cache_hit=True, retries=0, input_tokens=0, output_tokens=0)
        return note

    client = client or LLMClient()
    system_prompt = SYSTEM_PROMPT + language_instruction(lang)
    prompt = f"Ticker: {ticker}\nProduce the research note JSON now."
    last_error: Exception | None = None

    for attempt in range(MAX_RETRIES + 1):
        text, input_tokens, output_tokens = client.complete(prompt, system_prompt=system_prompt)
        try:
            payload = json.loads(text)
            validated = ResearchNoteSchema.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = exc
            prompt = (
                f"Ticker: {ticker}\nYour previous response failed schema validation: {exc}\n"
                "Return ONLY the corrected JSON object, nothing else."
            )
            continue

        note = validated.model_dump()
        note["model"] = MODEL
        await redis.set(_cache_key(ticker, lang), json.dumps(note), ex=settings.LLM_CACHE_TTL_HOURS * 3600)
        note.update(cache_hit=False, retries=attempt, input_tokens=input_tokens, output_tokens=output_tokens)
        return note

    raise ValueError(
        f"LLM failed to produce a schema-valid research note after {MAX_RETRIES} retries: {last_error}"
    )
