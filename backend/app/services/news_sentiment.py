"""Per-ticker news sentiment: pulls recent headlines (yfinance — no scraping, no new API
key) and has the LLM classify each headline's likely stock-price impact as high/medium/low,
with a one-line reason. Uses the shared structured_completion helper for schema validation,
retry-with-repair and Redis caching, like llm_research.py.

Chinese-market sources (华尔街见闻/新浪财经) don't apply here — this platform's universe is
US equities (see data_ingestion.py), so yfinance's own news feed is the in-scope source.
"""
import json
import re
import time
from curl_cffi import requests as news_requests

import yfinance as yf
from redis.asyncio import Redis

from app.config import settings
from app.schemas.news_sentiment import NewsSentimentSchema
from app.services.i18n import DEFAULT_LANG, language_instruction
from app.services.llm_research import (
    MAX_RETRIES as MAX_RETRIES,  # 保留本模块的历史导入路径（调用方与测试从这里取）
    LLMClient,
    read_cached_payload,
    structured_completion,
)

MAX_HEADLINES = 10
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
    if symbol.upper().endswith((".SS", ".SZ", ".SH", ".BJ")) or symbol.isdigit():
        code = re.sub(r"\D", "", symbol)[:6]
        query = {"uid":"", "keyword":code, "type":["cmsArticleWebOld"], "client":"web", "clientType":"web", "clientVersion":"curr", "param":{"cmsArticleWebOld":{"searchScope":"default", "sort":"default", "pageIndex":1, "pageSize":MAX_HEADLINES, "preTag":"", "postTag":""}}}
        callback = "jQuery35101792940631092459_1764599530165"
        response = news_requests.get("https://search-api-web.eastmoney.com/search/jsonp", params={"cb":callback, "param":json.dumps(query, ensure_ascii=False), "_":str(int(time.time()*1000))}, headers={"User-Agent":"Mozilla/5.0", "Referer":"https://so.eastmoney.com/"}, timeout=10)
        response.raise_for_status()
        raw = response.text.strip()
        if raw.startswith(callback+"("):
            raw = raw[len(callback)+1:].rstrip(";\n ")[:-1]
        if not raw:
            raise ValueError("真实资讯接口返回空响应")
        data = json.loads(raw)
        rows = data.get("result", {}).get("cmsArticleWebOld", [])
        if not isinstance(rows, list):
            raise ValueError("真实A股资讯接口返回结构变化")
        return [{"title":re.sub("<[^>]+>", "", row.get("title", "")), "summary":re.sub("<[^>]+>", "", row.get("content", ""))[:500], "published_at":row.get("date"), "publisher":row.get("mediaName", "东方财富资讯"), "url":"https://finance.eastmoney.com/a/"+row["code"]+".html"} for row in rows if row.get("title") and row.get("code")]
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
    cache_key = _cache_key(symbol, lang)
    # Read the cache before fetching headlines so a cache hit never touches the news source.
    cached = await read_cached_payload(redis, cache_key)
    if cached is not None:
        return cached

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
        await redis.set(cache_key, json.dumps(payload), ex=settings.NEWS_CACHE_TTL_HOURS * 3600)
        return payload

    def validate_model(validated: NewsSentimentSchema) -> None:
        if len(validated.items) != len(headlines):
            raise ValueError(f"expected {len(headlines)} classifications, got {len(validated.items)}")

    def payload_from_model(validated: NewsSentimentSchema) -> dict:
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

        return {
            "symbol": symbol,
            "items": items,
            "overall_signal": overall_signal,
            "avg_impact_score": round(avg_score, 2),
            "high_impact_count": high_count,
            "cache_hit": False,
        }

    result = await structured_completion(
        redis,
        client,
        NewsSentimentSchema,
        _build_prompt(headlines),
        cache_key=cache_key,
        cache_ttl_hours=settings.NEWS_CACHE_TTL_HOURS,
        system_prompt=SYSTEM_PROMPT + language_instruction(lang),
        repair_prompt=lambda exc: (
            _build_prompt(headlines)
            + f"\n\nYour previous response was invalid: {exc}\nReturn ONLY the corrected JSON object."
        ),
        payload_from_model=payload_from_model,
        validate_model=validate_model,
        error_message="LLM failed to produce schema-valid news classification",
    )
    return result.payload
