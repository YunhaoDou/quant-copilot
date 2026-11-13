#!/usr/bin/env python3
"""
SEC Filing Downloader & Parser.

Downloads and parses 10-K/10-Q/8-K filings from SEC EDGAR.
Uses SEC XBRL API for structured financial data + HTML download for MD&A text.
"""
import json
import re
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from . import paths as cfg

# GAAP concept mapping for financial statements
INCOME_STATEMENT_CONCEPTS = {
    "revenue": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
    "revenue_alt": "us-gaap:RevenueFromContractWithCustomer",
    "cost_of_revenue": "us-gaap:CostOfRevenue",
    "gross_profit": "us-gaap:GrossProfit",
    "operating_income": "us-gaap:OperatingIncomeLoss",
    "net_income": "us-gaap:NetIncomeLoss",
    "net_income_attributable": "us-gaap:NetIncomeLossAvailableToCommonStockholdersBasic",
    "eps_basic": "us-gaap:EarningsPerShareBasic",
    "eps_diluted": "us-gaap:EarningsPerShareDiluted",
    "rd_expense": "us-gaap:ResearchAndDevelopmentExpense",
    "sga_expense": "us-gaap:SellingGeneralAndAdministrativeExpense",
    "total_operating_expense": "us-gaap:OperatingExpenses",
    "interest_expense": "us-gaap:InterestExpense",
    "interest_income": "us-gaap:InterestIncomeExpenseNonoperating",
    "income_tax": "us-gaap:IncomeTaxExpenseBenefit",
    "depreciation_amortization": "us-gaap:DepreciationAndAmortization",
}

BALANCE_SHEET_CONCEPTS = {
    "total_assets": "us-gaap:Assets",
    "current_assets": "us-gaap:AssetsCurrent",
    "cash_and_equivalents": "us-gaap:CashAndCashEquivalentsAtCarryingValue",
    "short_term_investments": "us-gaap:ShortTermInvestments",
    "accounts_receivable": "us-gaap:AccountsReceivableNetCurrent",
    "inventory": "us-gaap:InventoryNet",
    "total_liabilities": "us-gaap:Liabilities",
    "current_liabilities": "us-gaap:LiabilitiesCurrent",
    "long_term_debt": "us-gaap:LongTermDebtNoncurrent",
    "short_term_debt": "us-gaap:ShortTermBorrowings",
    "total_equity": "us-gaap:StockholdersEquity",
    "retained_earnings": "us-gaap:RetainedEarningsAccumulatedDeficit",
    "goodwill": "us-gaap:Goodwill",
    "intangible_assets": "us-gaap:IntangibleAssetsNetExcludingGoodwill",
}

CASH_FLOW_CONCEPTS = {
    "operating_cash_flow": "us-gaap:NetCashProvidedByUsedInOperatingActivities",
    "investing_cash_flow": "us-gaap:NetCashProvidedByUsedInInvestingActivities",
    "financing_cash_flow": "us-gaap:NetCashProvidedByUsedInFinancingActivities",
    "depreciation_amortization_cf": "us-gaap:DepreciationDepletionAndAmortization",
    "capex": "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
    "free_cash_flow": "us-gaap:FreeCashFlow",
    "stock_based_comp": "us-gaap:ShareBasedCompensation",
    "dividends_paid": "us-gaap:PaymentsOfDividends",
    "share_repurchases": "us-gaap:PaymentsForRepurchaseOfCommonStock",
}

ALL_CONCEPTS = {}
for d in [INCOME_STATEMENT_CONCEPTS, BALANCE_SHEET_CONCEPTS, CASH_FLOW_CONCEPTS]:
    ALL_CONCEPTS.update(d)


def get_company_facts(cik: str) -> dict:
    """
    Fetch XBRL company facts from SEC API.
    Returns all financial data filed by the company.
    """
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    try:
        resp = requests.get(url, headers={
            **cfg.SEC_HEADERS,
            "Accept": "application/json",
        }, timeout=30)
        resp.raise_for_status()
        time.sleep(0.2)  # Rate limiting
        return resp.json()
    except Exception as e:
        cfg.logger.error(f"Failed to fetch company facts for CIK {cik}: {e}")
        return {}


def extract_concept_values(facts_data: dict, concept: str,
                          period_type: str = "annual",
                          max_results: int = 4) -> list[dict]:
    """
    Extract values for a specific GAAP concept from company facts.

    Args:
        facts_data: Company facts JSON from SEC API
        concept: GAAP concept (e.g., "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax")
        period_type: "annual" (FY) or "quarterly" for 10-Q filing periods
        max_results: Number of most recent periods to return
    """
    try:
        # Strip namespace prefix to get short name
        short_concept = concept.split(":")[-1].split("/")[-1]

        units_data = facts_data.get("facts", {}).get("us-gaap", {})

        concept_data = units_data.get(short_concept)

        if not concept_data:
            return []

        # Check all units
        all_entries = []
        for unit, entries in concept_data.get("units", {}).items():
            for entry in entries:
                all_entries.append(entry)

        # Filter entries: annual = fiscal year (fp=FY), quarterly = Q periods
        filtered = []
        for entry in all_entries:
            fp = entry.get("fp", "")
            form = entry.get("form", "")
            if period_type == "annual":
                if fp == "FY" or form in ("10-K", "20-F"):
                    filtered.append(entry)
            elif period_type == "quarterly" or period_type == "Q":
                if fp and fp.startswith("Q"):
                    filtered.append(entry)
                elif form == "10-Q":
                    filtered.append(entry)

        if not filtered:
            # Fallback: use all entries sorted
            filtered = all_entries

        # Sort by end date descending, take most recent
        filtered.sort(key=lambda x: x.get("end", ""), reverse=True)
        results = filtered[:max_results]

        return [
            {
                "end_date": r.get("end", ""),
                "val": r.get("val"),
                "unit": r.get("unit", "USD"),
                "filed": r.get("filed", ""),
                "frame": r.get("frame", ""),
                "form": r.get("form", ""),
                "fy": r.get("fy"),
                "fp": r.get("fp", ""),
            }
            for r in results
        ]
    except Exception as e:
        cfg.logger.warning(f"Extract concept {concept} failed: {e}")
        return []


def download_filing_html(accession_number: str, cik: str) -> str:
    """
    Download the complete filing HTML from SEC EDGAR.
    Returns the HTML text content.
    """
    cik_no_pad = str(int(cik))
    acc_no_dash = accession_number.replace("-", "")

    # Try the main filing document
    urls_to_try = [
        f"{cfg.SEC_EDGAR_BASE}/Archives/edgar/data/{cik_no_pad}/{acc_no_dash}/{accession_number}.txt",
        f"{cfg.SEC_EDGAR_BASE}/Archives/edgar/data/{cik_no_pad}/{acc_no_dash}/{accession_number}-index.htm",
        f"{cfg.SEC_EDGAR_BASE}/Archives/edgar/data/{cik_no_pad}/{acc_no_dash}/{accession_number}-index.html",
    ]

    for url in urls_to_try:
        try:
            resp = requests.get(url, headers=cfg.SEC_HEADERS, timeout=30)
            resp.raise_for_status()
            time.sleep(0.2)
            return resp.text
        except Exception:
            continue

    return ""


def get_full_submission_url(cik: str, accession_number: str) -> str:
    """Get the URL for the full submission text file."""
    cik_no_pad = str(int(cik))
    acc_no_dash = accession_number.replace("-", "")
    return f"{cfg.SEC_EDGAR_BASE}/Archives/edgar/data/{cik_no_pad}/{acc_no_dash}/{accession_number}.txt"


def parse_mda_from_html(html_text: str) -> dict:
    """
    Parse MD&A (Management's Discussion and Analysis) section from filing HTML.
    Returns the text content and page reference.
    """
    if not html_text:
        return {"text": "", "found": False}

    soup = BeautifulSoup(html_text, "lxml")
    text_content = soup.get_text(separator="\n")

    # Look for MD&A section
    mda_patterns = [
        r"(?i)ITEM\s*7\.\s*MANAGEMENT['’]S\s+DISCUSSION\s+(?:AND|&)\s+ANALYSIS",
        r"(?i)MANAGEMENT['’]S\s+DISCUSSION\s+(?:AND|&)\s+ANALYSIS\s+OF\s+FINANCIAL\s+CONDITION",
        r"(?i)ITEM\s*2\.\s*MANAGEMENT['’]S\s+DISCUSSION",
    ]

    mda_section = ""
    found = False
    for pattern in mda_patterns:
        m = re.search(pattern, text_content)
        if m:
            # Extract ~5000 chars after the MD&A start
            start = max(0, m.start() - 100)
            mda_section = text_content[start:start + 15000]
            found = True
            break

    # Also try to find risk factors
    risk_section = ""
    risk_pattern = re.search(r"(?i)ITEM\s*1[AA]\.\s*RISK\s+FACTORS", text_content)
    if risk_pattern:
        start = max(0, risk_pattern.start() - 100)
        risk_section = text_content[start:start + 8000]

    # Find forward-looking statements / guidance
    guidance_section = ""
    guidance_patterns = [
        r"(?i)FORWARD-LOOKING\s+STATEMENTS?",
        r"(?i)OUTLOOK\s+(?:FOR|AND)\s+\d{4}",
        r"(?i)FISCAL\s+\d{4}\s+OUTLOOK",
        r"(?i)GUIDANCE",
    ]
    for pat in guidance_patterns:
        m = re.search(pat, text_content)
        if m:
            start = max(0, m.start() - 200)
            guidance_section = text_content[start:start + 5000]
            break

    return {
        "mda_text": mda_section[:10000],
        "risk_factors": risk_section[:5000],
        "guidance_outlook": guidance_section[:5000],
        "found": found,
    }


def extract_footnotes(html_text: str) -> list[str]:
    """Extract key footnote sections from the filing."""
    if not html_text:
        return []

    soup = BeautifulSoup(html_text, "lxml")
    text = soup.get_text(separator="\n")

    # Look for footnotes / notes to financial statements
    footnote_markers = [
        r"(?i)(?:NOTES?\s+TO\s+(?:THE\s+)?(?:CONSOLIDATED\s+)?FINANCIAL\s+STATEMENTS)",
        r"(?i)(?:NOTES?\s+TO\s+FINANCIAL\s+STATEMENTS)",
    ]

    notes = []
    for marker in footnote_markers:
        matches = list(re.finditer(marker, text))
        for m in matches:
            start = m.start()
            note_text = text[start:start + 5000]
            notes.append(note_text[:3000])

    return notes[:5]  # Max 5 footnotes


def build_financial_summary(facts_data: dict, filing_date: str) -> dict:
    """
    Build a structured financial summary from XBRL company facts.
    Extracts the most recent annual and quarterly data for key metrics.
    """
    summary = {
        "income_statement": {},
        "balance_sheet": {},
        "cash_flow": {},
        "ratios": {},
        "reporting_date": filing_date,
    }

    # Extract income statement items
    for label, concept in INCOME_STATEMENT_CONCEPTS.items():
        values = extract_concept_values(facts_data, concept, period_type="annual", max_results=2)
        if not values:
            # Try with the us-gaap prefix variations
            alt_concept = concept.replace("us-gaap:", "us-gaap/")
            values = extract_concept_values(facts_data, alt_concept, period_type="annual", max_results=2)
        if values:
            summary["income_statement"][label] = values

    # Balance sheet
    for label, concept in BALANCE_SHEET_CONCEPTS.items():
        values = extract_concept_values(facts_data, concept, period_type="annual", max_results=2)
        if values:
            summary["balance_sheet"][label] = values

    # Cash flow
    for label, concept in CASH_FLOW_CONCEPTS.items():
        values = extract_concept_values(facts_data, concept, period_type="annual", max_results=2)
        if values:
            summary["cash_flow"][label] = values

    # Calculate key ratios
    summary["ratios"] = calculate_ratios(summary)

    return summary


def calculate_ratios(financial_summary: dict) -> dict:
    """Calculate financial ratios from extracted data."""
    ratios = {}
    is_ = financial_summary.get("income_statement", {})
    bs = financial_summary.get("balance_sheet", {})
    cf = financial_summary.get("cash_flow", {})

    def latest(values_list):
        return values_list[0]["val"] if values_list else None

    def prev(values_list):
        return values_list[1]["val"] if values_list and len(values_list) > 1 else None

    rev = latest(is_.get("revenue"))
    ni = latest(is_.get("net_income"))
    gp = latest(is_.get("gross_profit"))
    op_income = latest(is_.get("operating_income"))
    total_assets = latest(bs.get("total_assets"))
    total_equity = latest(bs.get("total_equity"))
    ocf = latest(cf.get("operating_cash_flow"))
    capex = latest(cf.get("capex"))

    if rev and rev != 0:
        if ni: ratios["net_margin"] = round(ni / rev * 100, 2)
        if gp: ratios["gross_margin"] = round(gp / rev * 100, 2)
        if op_income: ratios["operating_margin"] = round(op_income / rev * 100, 2)
    if total_equity and total_equity != 0 and ni:
        ratios["roe"] = round(ni / total_equity * 100, 2)
    if total_assets and total_assets != 0 and ni:
        ratios["roa"] = round(ni / total_assets * 100, 2)
    if ocf and ni and ni != 0:
        ratios["ocf_to_ni"] = round(ocf / ni, 2)
    if capex and ocf:
        ratios["fcf"] = ocf + capex  # capex is negative

    # YoY change
    rev_prev = prev(is_.get("revenue"))
    ni_prev = prev(is_.get("net_income"))
    if rev_prev and rev_prev != 0 and rev:
        ratios["revenue_yoy_change_pct"] = round((rev - rev_prev) / abs(rev_prev) * 100, 2)
    if ni_prev and ni_prev != 0 and ni:
        ratios["net_income_yoy_change_pct"] = round((ni - ni_prev) / abs(ni_prev) * 100, 2)

    return ratios


def get_cik_data_dir(cik: str) -> Path:
    """Get per-CIK data directory for cached filings."""
    d = cfg.DATA_DIR / "filings" / cik
    d.mkdir(parents=True, exist_ok=True)
    return d


def process_filing(ticker: str, cik: str, form_type: str,
                   filing_date: str, link: str = "") -> dict:
    """
    Process a single filing: download, parse, and extract financial data.

    Returns a structured analysis-ready dict.
    """
    cfg.logger.info(f"Processing {form_type} for {ticker} (CIK: {cik})")

    result = {
        "ticker": ticker,
        "cik": cik,
        "form_type": form_type,
        "filing_date": filing_date,
        "status": "processing",
        "financial_summary": {},
        "mda": {},
        "footnotes": [],
        "raw_text_length": 0,
    }

    try:
        # Fetch XBRL company facts (includes ALL historical data)
        facts_data = get_company_facts(cik)
        has_xbrl = bool(facts_data)

        # Extract accession number from the link
        accession_number = ""
        if link:
            m = re.search(r'/(\d{10,20}-\d{2}-\d{6})/', link)
            if m:
                accession_number = m.group(1)

        # Download HTML for MD&A and footnotes
        html_text = ""
        if accession_number:
            html_text = download_filing_html(accession_number, cik)

        # Build financial summary from XBRL
        if has_xbrl:
            financial_summary = build_financial_summary(facts_data, filing_date)
            result["financial_summary"] = financial_summary

        # Parse MD&A from HTML
        if html_text:
            mda = parse_mda_from_html(html_text)
            result["mda"] = mda
            result["raw_text_length"] = len(html_text)

            footnotes = extract_footnotes(html_text)
            result["footnotes"] = footnotes

        result["status"] = "completed"
        cfg.logger.info(f"  ✓ {ticker} {form_type} processed. "
                        f"XBRL: {'✓' if has_xbrl else '✗'}, "
                        f"HTML: {result['raw_text_length']:,} chars")

    except Exception as e:
        cfg.logger.error(f"Failed to process {ticker} {form_type}: {e}")
        result["status"] = "error"
        result["error"] = str(e)

    return result


def process_pending_filings() -> list[dict]:
    """Process all pending filings from the queue."""
    pending_file = cfg.DATA_DIR / "pending_filings.json"
    if not pending_file.exists():
        cfg.logger.info("No pending filings to process")
        return []

    with open(pending_file) as f:
        pending = json.load(f)

    cfg.logger.info(f"Processing {len(pending)} pending filings...")
    results = []

    for filing in pending:
        r = process_filing(
            ticker=filing.get("ticker", ""),
            cik=filing.get("cik", ""),
            form_type=filing.get("form_type", ""),
            filing_date=filing.get("filing_date", ""),
            link=filing.get("link", ""),
        )
        results.append(r)

        # Save interim result
        output = cfg.TODAY_DIR / "processed" / f"{r['ticker']}_{r['form_type']}_{r['filing_date'][:10]}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w") as f:
            json.dump(r, f, indent=2, ensure_ascii=False, default=str)

        # Rate limiting
        time.sleep(0.5)

    # Save all results
    all_output = cfg.TODAY_DIR / "processed" / f"all_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(all_output, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)

    # Clear pending queue
    pending_file.unlink()

    cfg.logger.info(f"Processed {len(results)} filings. Output: {all_output}")
    return results
