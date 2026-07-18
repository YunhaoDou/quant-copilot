#!/usr/bin/env python3
"""Grounded equity research note CLI — real fundamentals + real news, LLM only summarizes.

Fetches trailing/forward P/E, margins, revenue growth, sector, market cap via yfinance,
plus the 5 most recent real news headlines. Injects those facts into the LLM prompt and
instructs it to cite which fact backs each catalyst/risk — the model is not allowed to
invent numbers. Prints the fact block alongside the note so the reader can verify nothing
was hallucinated.

Requires an OpenAI-compatible chat completions endpoint (DeepSeek by default).
Env vars: LLM_API_KEY (required), LLM_BASE_URL (default DeepSeek), LLM_MODEL (default deepseek-chat).
"""
import argparse
import json
import os

import httpx
import yfinance as yf

MAX_RETRIES = 2
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"

FUNDAMENTAL_KEYS = [
    ("sector", "行业"),
    ("marketCap", "市值"),
    ("currentPrice", "现价"),
    ("trailingPE", "静态PE"),
    ("forwardPE", "动态PE"),
    ("profitMargins", "净利率"),
    ("revenueGrowth", "营收增速"),
    ("returnOnEquity", "ROE"),
    ("totalRevenue", "总营收"),
    ("recommendationKey", "分析师评级"),
]

SYSTEM_PROMPT = (
    "You are an equity research assistant. You will be given REAL fetched fundamentals and "
    "REAL recent news headlines for a ticker. Base your thesis, catalysts, and risks ONLY on "
    "the facts provided — do not invent numbers or events not present in the input. Each "
    "catalyst and risk must reference which fact or headline it is based on (in parentheses). "
    'Respond with ONLY a JSON object matching: {"thesis": str, "catalysts": [str], "risks": '
    '[str], "fair_value_low": float, "fair_value_high": float}. No prose outside the JSON.'
)


def fetch_fundamentals(ticker: str) -> dict:
    info = yf.Ticker(ticker.upper()).info
    return {label: info.get(key) for key, label in FUNDAMENTAL_KEYS}


def fetch_news(ticker: str, limit: int = 5) -> list[dict]:
    raw = yf.Ticker(ticker.upper()).news or []
    out = []
    for item in raw[:limit]:
        content = item.get("content", item)
        out.append(
            {
                "title": content.get("title", ""),
                "published": content.get("pubDate", ""),
                "url": (content.get("canonicalUrl") or {}).get("url", ""),
            }
        )
    return out


def build_fact_block(ticker: str, fundamentals: dict, news: list[dict]) -> str:
    lines = [f"Ticker: {ticker.upper()}", "", "Fundamentals:"]
    for label, value in fundamentals.items():
        lines.append(f"  {label}: {value}")
    lines.append("")
    lines.append("Recent news:")
    for i, n in enumerate(news, 1):
        lines.append(f"  {i}. [{n['published']}] {n['title']}")
    return "\n".join(lines)


def call_llm(fact_block: str, api_key: str, base_url: str, model: str) -> tuple[dict, int]:
    prompt = f"{fact_block}\n\nProduce the research note JSON now, grounded strictly in the facts above."
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        resp = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.3,
                "max_tokens": 1024,
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
        try:
            payload = json.loads(text)
            _validate(payload)
            return payload, attempt
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            prompt = (
                f"{fact_block}\n\nYour previous response failed validation: {exc}\n"
                "Return ONLY the corrected JSON object, nothing else."
            )
    raise ValueError(f"LLM failed to produce a valid research note after {MAX_RETRIES} retries: {last_error}")


def _validate(payload: dict) -> None:
    required = {"thesis", "catalysts", "risks", "fair_value_low", "fair_value_high"}
    missing = required - payload.keys()
    if missing:
        raise ValueError(f"missing fields: {missing}")
    if len(payload["thesis"]) < 10:
        raise ValueError("thesis too short")
    if not payload["catalysts"] or not payload["risks"]:
        raise ValueError("catalysts/risks must be non-empty")
    if payload["fair_value_high"] < payload["fair_value_low"]:
        raise ValueError("fair_value_high must be >= fair_value_low")


def print_note(ticker: str, fundamentals: dict, news: list[dict], note: dict, retries: int) -> None:
    print(f"=== {ticker.upper()} 研究笔记（依据 {len(news)} 条真实新闻 + 真实基本面，{retries} 次重试）===\n")
    print("依据（基本面）：")
    for label, value in fundamentals.items():
        print(f"  {label}: {value}")
    print("\n依据（新闻）：")
    for i, n in enumerate(news, 1):
        print(f"  {i}. {n['title']}")
    print(f"\nThesis:\n  {note['thesis']}")
    print("\nCatalysts:")
    for c in note["catalysts"]:
        print(f"  - {c}")
    print("\nRisks:")
    for r in note["risks"]:
        print(f"  - {r}")
    print(f"\nFair value range: {note['fair_value_low']:.2f} - {note['fair_value_high']:.2f}")
    print("\n免责声明：模型估值区间仅供参考，不构成投资建议。")


def main():
    parser = argparse.ArgumentParser(description="Grounded ticker research note — real data, LLM only summarizes")
    parser.add_argument("--ticker", required=True, help="e.g. AAPL")
    parser.add_argument("--news-limit", type=int, default=5)
    args = parser.parse_args()

    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        raise SystemExit("LLM_API_KEY not set. export LLM_API_KEY=sk-... (DeepSeek key by default)")
    base_url = os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL)
    model = os.environ.get("LLM_MODEL", DEFAULT_MODEL)

    fundamentals = fetch_fundamentals(args.ticker)
    news = fetch_news(args.ticker, args.news_limit)
    fact_block = build_fact_block(args.ticker, fundamentals, news)

    note, retries = call_llm(fact_block, api_key, base_url, model)
    print_note(args.ticker, fundamentals, news, note, retries)


if __name__ == "__main__":
    main()
