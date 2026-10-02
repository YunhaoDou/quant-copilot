"""Per-ticker news sentiment: pulls recent headlines (yfinance — no scraping, no new API
key) and has the LLM classify each headline's likely stock-price impact as high/medium/low,
with a one-line reason. Schema-validated with retry, Redis-cached like llm_research.py.

Chinese-market sources (华尔街见闻/新浪财经) don't apply here — this platform's universe is
US equities (see data_ingestion.py), so yfinance's own news feed is the in-scope source.
"""
import json

import yfinance as yf
from pydantic import ValidationError
from redis.asyncio import Redis

from app.config import settings
from app.schemas.news_sentiment import NewsSentimentSchema
from app.services.i18n import DEFAULT_LANG, language_instruction
from app.services.llm_research import LLMClient

MAX_HEADLINES = 10
MAX_RETRIES = 2
IMPACT_WEIGHT = {"high": 3, "medium": 2, "low": 1}

SYSTEM_PROMPT = (
    "You are a markets news analyst. Given a numbered list of recent headlines for a stock, "
    "classify EACH headline's likely near-term impact on the stock's price as \"high\", "
    "\"medium\", or \"low\", with a short reason. Respond with ONLY a JSON object "
    '{"items": [{"index": int, "impact": "high"|"medium"|"low", "reason": str}, ...]} '
    "containing exactly one entry per headline, in the same order. No prose outside the JSON."
)


def _cache_key(symbol: str, lang: str) -> str:
    return f"news_sentiment:{symbol}:{lang}"


def _fetch_headlines(symbol: str) -> list[dict]:
    raw = yf.Ticker(symbol.upper()).news or []
    headlines = []
    for item in raw[:MAX_HEADLINES]:
        content = item.get("content", {})
        title = content.get("title")
        if not title:
            continue
        headlines.append(
            {
                "title": title,
                "summary": content.get("summary", ""),
                "published_at": content.get("pubDate"),
                "publisher": (content.get("provider") or {}).get("displayName", "unknown"),
                "url": (content.get("canonicalUrl") or {}).get("url", ""),
            }
        )
    return headlines


def _build_prompt(headlines: list[dict]) -> str:
    lines = [f"{i}. {h['title']} — {h['summary']}".strip(" —") for i, h in enumerate(headlines)]
    return "Headlines:\n" + "\n".join(lines) + "\n\nClassify each headline now."


async def get_news_sentiment(
    redis: Redis, symbol: str, client: LLMClient | None = None, lang: str = DEFAULT_LANG
) -> dict:
    symbol = symbol.upper()
    cached = await redis.get(_cache_key(symbol, lang))
    if cached:
        payload = json.loads(cached)
        payload["cache_hit"] = True
        return payload

    headlines = _fetch_headlines(symbol)
    if not headlines:
        payload = {
            "symbol": symbol,
            "items": [],
            "overall_signal": "quiet",
            "avg_impact_score": 0.0,
            "high_impact_count": 0,
            "cache_hit": False,
        }
        await redis.set(_cache_key(symbol, lang), json.dumps(payload), ex=settings.NEWS_CACHE_TTL_HOURS * 3600)
        return payload

    client = client or LLMClient()
    system_prompt = SYSTEM_PROMPT + language_instruction(lang)
    prompt = _build_prompt(headlines)
    last_error: Exception | None = None

    for _attempt in range(MAX_RETRIES + 1):
        text, _in_tok, _out_tok = client.complete(prompt, system_prompt=system_prompt)
        try:
            data = json.loads(text)
            validated = NewsSentimentSchema.model_validate(data)
            if len(validated.items) != len(headlines):
                raise ValueError(f"expected {len(headlines)} classifications, got {len(validated.items)}")
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = exc
            prompt = (
                _build_prompt(headlines)
                + f"\n\nYour previous response was invalid: {exc}\nReturn ONLY the corrected JSON object."
            )
            continue

        items = []
        weighted_sum = 0
        high_count = 0
        for classification in sorted(validated.items, key=lambda c: c.index):
            h = headlines[classification.index]
            weighted_sum += IMPACT_WEIGHT[classification.impact]
            if classification.impact == "high":
                high_count += 1
            items.append({**h, "impact": classification.impact, "reason": classification.reason})

        avg_score = weighted_sum / len(items)
        overall_signal = "high" if avg_score >= 2.5 else "medium" if avg_score >= 1.5 else "low"

        payload = {
            "symbol": symbol,
            "items": items,
            "overall_signal": overall_signal,
            "avg_impact_score": round(avg_score, 2),
            "high_impact_count": high_count,
            "cache_hit": False,
        }
        await redis.set(_cache_key(symbol, lang), json.dumps(payload), ex=settings.NEWS_CACHE_TTL_HOURS * 3600)
        return payload

    raise ValueError(f"LLM failed to produce schema-valid news classification after {MAX_RETRIES} retries: {last_error}")
