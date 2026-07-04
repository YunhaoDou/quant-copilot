"""LLM-backed structured research notes: ticker -> thesis / catalysts / risks / fair value.

Schema-validated with automatic retry on validation failure (the model is told exactly
what broke and asked to fix it), and Redis-cached per ticker for LLM_CACHE_TTL_HOURS so a
repeat request within the window doesn't re-spend tokens.
"""
import json

from anthropic import Anthropic
from pydantic import ValidationError
from redis.asyncio import Redis

from app.config import settings
from app.schemas.research import ResearchNoteSchema

MODEL = "claude-sonnet-4-5"
MAX_RETRIES = 2

SYSTEM_PROMPT = (
    "You are an equity research assistant. Given a ticker, produce a structured research "
    'note. Respond with ONLY a JSON object matching this schema: {"thesis": str, '
    '"catalysts": [str], "risks": [str], "fair_value_low": float, "fair_value_high": float}. '
    "No prose outside the JSON."
)


class LLMClient:
    """Thin wrapper around the Anthropic SDK so tests can inject a fake in its place."""

    def __init__(self, api_key: str | None = None):
        self._client = Anthropic(api_key=api_key or settings.ANTHROPIC_API_KEY)

    def complete(self, prompt: str) -> tuple[str, int, int]:
        response = self._client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return text, response.usage.input_tokens, response.usage.output_tokens


def _cache_key(ticker: str) -> str:
    return f"research_note:{ticker}"


async def get_research_note(redis: Redis, ticker: str, client: LLMClient | None = None) -> dict:
    """Returns a schema-validated research-note dict. Reads/writes the Redis cache."""
    cached = await redis.get(_cache_key(ticker))
    if cached:
        note = json.loads(cached)
        note.update(cache_hit=True, retries=0, input_tokens=0, output_tokens=0)
        return note

    client = client or LLMClient()
    prompt = f"Ticker: {ticker}\nProduce the research note JSON now."
    last_error: Exception | None = None

    for attempt in range(MAX_RETRIES + 1):
        text, input_tokens, output_tokens = client.complete(prompt)
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
        await redis.set(_cache_key(ticker), json.dumps(note), ex=settings.LLM_CACHE_TTL_HOURS * 3600)
        note.update(cache_hit=False, retries=attempt, input_tokens=input_tokens, output_tokens=output_tokens)
        return note

    raise ValueError(
        f"LLM failed to produce a schema-valid research note after {MAX_RETRIES} retries: {last_error}"
    )
