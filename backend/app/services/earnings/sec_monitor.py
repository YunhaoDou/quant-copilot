#!/usr/bin/env python3
"""
SEC EDGAR Monitor — watch for new 10-K, 10-Q, 8-K filings from watchlist companies.

Uses SEC EDGAR RSS feed and CIK-based filtering.
"""
import hashlib
import json
import re
import time
from datetime import datetime, timezone, timedelta

import feedparser
import requests

from . import paths as cfg

PROCESSED_FILE = cfg.DATA_DIR / "processed_filings.json"
CIK_TO_TICKER = {}


def load_watchlist() -> list[dict]:
    if not cfg.ALL_COMPANIES_FILE.exists():
        cfg.logger.error(f"Watchlist not found at {cfg.ALL_COMPANIES_FILE}")
        cfg.logger.info("Run companies.build_watchlist() first to build the watchlist")
        return []
    with open(cfg.ALL_COMPANIES_FILE) as f:
        companies = json.load(f)
    global CIK_TO_TICKER
    for c in companies:
        if c.get("cik"):
            CIK_TO_TICKER[c["cik"]] = c
    cfg.logger.info(f"Watchlist loaded: {len(companies)} companies, {len(CIK_TO_TICKER)} with CIK")
    return companies


def load_processed_filings() -> set:
    if PROCESSED_FILE.exists():
        with open(PROCESSED_FILE) as f:
            return set(json.load(f))
    return set()


def save_processed_filing(filing_id: str):
    processed = load_processed_filings()
    processed.add(filing_id)
    with open(PROCESSED_FILE, "w") as f:
        json.dump(sorted(processed)[-10000:], f)


def query_sec_rss(form_types: list[str], lookback_hours: int = 12) -> list[dict]:
    all_filings = []
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    for form_type in form_types:
        url = (
            f"{cfg.SEC_EDGAR_BASE}/cgi-bin/browse-edgar"
            f"?action=getcurrent&type={form_type}&count=100&output=atom"
        )

        retries = 3
        feed_entries = []
        for attempt in range(retries):
            try:
                resp = requests.get(url, headers=cfg.SEC_HEADERS, timeout=60)
                resp.raise_for_status()
                feed = feedparser.parse(resp.content)
                feed_entries = feed.get("entries", [])
                break
            except Exception as e:
                cfg.logger.warning(f"RSS {form_type} attempt {attempt+1}/{retries}: {e}")
                if attempt < retries - 1:
                    time.sleep(2**attempt + 1)

        # SEC rate limiting
        time.sleep(1.0)

        for entry in feed_entries:
            try:
                filing_date = entry.updated_parsed
                if filing_date:
                    from time import mktime
                    filing_date = datetime.fromtimestamp(mktime(filing_date), tz=timezone.utc)
                else:
                    filing_date = datetime.now(timezone.utc)
            except Exception:
                filing_date = datetime.now(timezone.utc)

            if filing_date < cutoff_time:
                continue

            # Extract CIK from title: "10-K - Company Name (0001234567) (Filer)"
            title = entry.get("title", "")
            cik = ""
            m = re.search(r'\((\d{10})\)', title)
            if m:
                cik = m.group(1)
            else:
                m = re.search(r'\((\d{1,10})\)', title)
                if m:
                    cik = m.group(1).zfill(10)

            # Fallback: summary / links
            if not cik:
                summary = entry.get("summary", "") or ""
                m = re.search(r'CIK=(\d+)', summary)
                if m:
                    cik = m.group(1).zfill(10)
            if not cik:
                for link in entry.get("links", []):
                    href = link.get("href", "")
                    m = re.search(r'CIK=(\d+)', href)
                    if m:
                        cik = m.group(1).zfill(10)
                        break

            filing = {
                "form_type": form_type,
                "company_name": title.split(" - ")[-1].replace("(Filer)", "").strip() if " - " in title else title,
                "cik": cik,
                "filing_date": filing_date.isoformat(),
                "title": title,
                "summary": entry.get("summary", ""),
                "link": entry.get("link", ""),
                "filing_id": hashlib.md5(f"{cik}_{form_type}_{filing_date.isoformat()}".encode()).hexdigest()[:16],
            }
            all_filings.append(filing)

        cfg.logger.info(f"RSS {form_type}: {len(feed_entries)} entries, "
                        f"{sum(1 for f in all_filings if f['form_type'] == form_type)} in window")

    return all_filings


def filter_watchlist_filings(filings: list[dict]) -> list[dict]:
    matched = []
    for filing in filings:
        cik = filing.get("cik", "")
        if cik in CIK_TO_TICKER:
            company = CIK_TO_TICKER[cik]
            filing["ticker"] = company["ticker"]
            filing["company_name"] = company["name"]
            matched.append(filing)
    cfg.logger.info(f"Watchlist matches: {len(matched)} out of {len(filings)} total filings")
    return matched


def find_new_filings(form_types: list[str] = None, lookback_hours: int = 12) -> list[dict]:
    if form_types is None:
        form_types = ["10-K", "10-Q", "8-K"]

    companies = load_watchlist()
    if not companies:
        return []

    processed = load_processed_filings()
    all_filings = query_sec_rss(form_types, lookback_hours)
    matched = filter_watchlist_filings(all_filings)

    new_filings = []
    for filing in matched:
        if filing["filing_id"] not in processed:
            new_filings.append(filing)
            save_processed_filing(filing["filing_id"])

    cfg.logger.info(f"New filings found: {len(new_filings)}")
    for f in new_filings:
        cfg.logger.info(f"  [{f['form_type']}] {f['ticker']} ({f['company_name'][:30]}) — {f['filing_date'][:19]}")

    return new_filings


def save_pending_filings(filings: list[dict]):
    pending_file = cfg.DATA_DIR / "pending_filings.json"
    with open(pending_file, "w") as f:
        json.dump(filings, f, indent=2, ensure_ascii=False)
    cfg.logger.info(f"Pending filings saved: {len(filings)} to {pending_file}")
