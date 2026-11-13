#!/usr/bin/env python3
"""
Fetch NASDAQ 100 and S&P 500 component companies with CIK numbers.

Data sources:
  - NASDAQ100: NASDAQ Trader API
  - S&P500: Wikipedia (public list)
  - CIK lookup: SEC company_tickers.json
"""
import json
import re

import requests

from . import paths as cfg


def fetch_sec_cik_lookup() -> dict:
    """Download the master CIK lookup from SEC."""
    url = f"{cfg.SEC_EDGAR_BASE}/files/company_tickers.json"
    resp = requests.get(url, headers=cfg.SEC_HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # Build ticker -> {cik, name} mapping
    lookup = {}
    for item in data.values():
        cik_str = str(item["cik_str"]).zfill(10)
        ticker = item["ticker"].upper()
        lookup[ticker] = {
            "cik": cik_str,
            "name": item["title"],
            "cik_int": item["cik_str"],
        }
    cfg.logger.info(f"SEC CIK lookup: {len(lookup)} companies loaded")
    return lookup


def fetch_nasdaq100_tickers() -> list[dict]:
    """Fetch NASDAQ 100 components from NASDAQ's official listing page."""
    url = "https://www.nasdaq.com/api/v1/assets/screener?nasdaq-100=true&limit=110"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        tickers = []
        for row in data.get("data", []):
            symbol = row.get("symbol", "").strip()
            if symbol:
                tickers.append({
                    "ticker": symbol.upper(),
                    "name": row.get("companyName", row.get("name", "")),
                    "sector": row.get("sector", ""),
                    "industry": row.get("industry", ""),
                })
        if tickers:
            cfg.logger.info(f"NASDAQ100: {len(tickers)} tickers fetched")
            return tickers
        raise ValueError("Empty response from NASDAQ API")
    except Exception as e:
        cfg.logger.warning(f"NASDAQ API v1 failed ({e}), trying v2...")
        return fetch_nasdaq100_v2()


def fetch_nasdaq100_v2() -> list[dict]:
    """Fallback: use NASDAQ's screener API directly."""
    url = "https://api.nasdaq.com/api/screener/stocks?exchange=nasdaq&marketcap=large"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        tickers = []
        for row in data.get("data", {}).get("rows", []):
            symbol = row.get("symbol", "").strip()
            if symbol:
                tickers.append({
                    "ticker": symbol.upper(),
                    "name": row.get("companyName", row.get("name", "")),
                    "sector": row.get("sector", ""),
                    "industry": row.get("industry", ""),
                })
        cfg.logger.info(f"NASDAQ screener v2: {len(tickers)} tickers")
        if tickers:
            # Filter to NASDAQ100-like companies (top 100 by market cap on NASDAQ)
            return tickers[:110]
        raise ValueError("Empty v2 response")
    except Exception as e:
        cfg.logger.warning(f"NASDAQ API v2 also failed ({e}), using Wikipedia fallback")
        return fetch_nasdaq100_fallback()


def fetch_nasdaq100_fallback() -> list[dict]:
    """Fallback: scrape NASDAQ 100 list from Wikipedia."""
    url = "https://en.wikipedia.org/wiki/Nasdaq-100"
    headers = {"User-Agent": cfg.SEC_HEADERS["User-Agent"]}
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "lxml")
        tables = soup.find_all("table", class_="wikitable")

        tickers = []
        # Table 4 is the components table (Ticker, Company, ICB Industry, ICB Subsector)
        for table in tables:
            header_text = table.find("tr").get_text() if table.find("tr") else ""
            if "Ticker" not in header_text or "Company" not in header_text:
                continue
            rows = table.find_all("tr")
            for row in rows[1:]:  # Skip header
                cols = row.find_all("td")
                if len(cols) >= 2:
                    ticker_cell = cols[0].get_text(strip=True)
                    name_cell = cols[1].get_text(strip=True)
                    ticker = re.sub(r'\[.*?\]', '', ticker_cell).strip().upper()
                    name = re.sub(r'\[.*?\]', '', name_cell).strip()
                    sector = cols[2].get_text(strip=True) if len(cols) > 2 else ""
                    industry = cols[3].get_text(strip=True) if len(cols) > 3 else ""
                    if ticker and len(ticker) <= 5 and not ticker.startswith("1,") and not ticker.startswith("2,"):
                        tickers.append({"ticker": ticker, "name": name, "sector": sector, "industry": industry})

        cfg.logger.info(f"NASDAQ100 (fallback): {len(tickers)} tickers fetched")
        return tickers
    except Exception as e:
        cfg.logger.error(f"NASDAQ100 fallback failed: {e}")
        return []


def fetch_sp500_tickers() -> list[dict]:
    """Fetch S&P 500 components from Wikipedia."""
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    headers = {"User-Agent": cfg.SEC_HEADERS["User-Agent"]}
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "lxml")
        table = soup.find("table", {"id": "constituents"})

        tickers = []
        if table:
            rows = table.find_all("tr")
            for row in rows[1:]:
                cols = row.find_all("td")
                if len(cols) >= 8:
                    ticker = cols[0].get_text(strip=True)
                    name = cols[1].get_text(strip=True)
                    sector = cols[3].get_text(strip=True) if len(cols) > 3 else ""
                    tickers.append({
                        "ticker": ticker.upper(),
                        "name": name,
                        "sector": sector,
                        "industry": cols[4].get_text(strip=True) if len(cols) > 4 else "",
                    })

        cfg.logger.info(f"SP500: {len(tickers)} tickers fetched")
        return tickers
    except Exception as e:
        cfg.logger.error(f"SP500 fetch failed: {e}")
        return []


def build_watchlist():
    """Build and save the master watchlist with CIK numbers."""
    cfg.logger.info("=== Building watchlist ===")

    # Fetch CIK lookup
    cik_lookup = fetch_sec_cik_lookup()

    # Save CIK lookup
    with open(cfg.CIK_LOOKUP_FILE, "w") as f:
        json.dump(cik_lookup, f, indent=2)

    # Fetch index components
    nasdaq100 = fetch_nasdaq100_tickers()
    sp500 = fetch_sp500_tickers()

    # Save raw lists
    with open(cfg.NASDAQ100_FILE, "w") as f:
        json.dump(nasdaq100, f, indent=2)
    with open(cfg.SP500_FILE, "w") as f:
        json.dump(sp500, f, indent=2)

    # Merge: NASDAQ100 + SP500, deduplicated, with CIK
    seen_tickers = set()
    all_companies = []

    for company in nasdaq100 + sp500:
        ticker = company["ticker"]
        if ticker in seen_tickers:
            continue
        seen_tickers.add(ticker)

        info = cik_lookup.get(ticker, {})
        company["cik"] = info.get("cik", "")
        company["sec_name"] = info.get("name", "")
        all_companies.append(company)

    with open(cfg.ALL_COMPANIES_FILE, "w") as f:
        json.dump(all_companies, f, indent=2)

    cfg.logger.info(f"Watchlist built: {len(all_companies)} unique companies "
                    f"(NASDAQ100: {len(nasdaq100)}, SP500: {len(sp500)})")
    return all_companies
