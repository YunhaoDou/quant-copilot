"""Path/config constants for the earnings pipeline (ported from earnings-bot/config.py).

Data now lives under backend/data/earnings/ instead of ~/earnings-bot/data/.
"""
import logging
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]  # backend/
DATA_DIR = BASE_DIR / "data" / "earnings"
COMPANIES_DIR = DATA_DIR / "companies"
REPORTS_DIR = DATA_DIR / "reports"
ARCHIVE_DIR = DATA_DIR / "archive"
LOGS_DIR = BASE_DIR / "logs"

# Date-based subdirectory for today's reports
TODAY = datetime.now().strftime("%Y%m%d")
TODAY_DIR = DATA_DIR / TODAY
REPORT_OUTPUT_DIR = TODAY_DIR / "reports"
FILING_CACHE_DIR = TODAY_DIR / "filings"

for d in [COMPANIES_DIR, REPORTS_DIR, ARCHIVE_DIR, LOGS_DIR, TODAY_DIR]:
    d.mkdir(parents=True, exist_ok=True)
(TODAY_DIR / "processed").mkdir(parents=True, exist_ok=True)
(TODAY_DIR / "reports").mkdir(parents=True, exist_ok=True)

# SEC EDGAR
SEC_EDGAR_BASE = "https://www.sec.gov"
SEC_HEADERS = {
    "User-Agent": "EarningsBot/1.0 (dyhao0909@gmail.com)",
    "Accept-Encoding": "gzip, deflate",
}

# Watchlist files
NASDAQ100_FILE = COMPANIES_DIR / "nasdaq100.json"
SP500_FILE = COMPANIES_DIR / "sp500.json"
ALL_COMPANIES_FILE = COMPANIES_DIR / "all_companies.json"
CIK_LOOKUP_FILE = COMPANIES_DIR / "cik_lookup.json"

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOGS_DIR / "earnings_bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("earnings_bot")
