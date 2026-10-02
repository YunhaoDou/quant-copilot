"""Pulls A-share fund NAV/price history via AKShare and upserts it into Postgres.

Two fund shapes, routed by code prefix (matches AKShare's own on-exchange vs. OTC split):
- ETF/LOF (on-exchange, codes starting 15/51/56/58 for ETF, 16/50 for LOF): daily close
  price from `fund_etf_hist_em` / `fund_lof_hist_em`.
- OTC (open-end, everything else): daily nav/acc_nav from `fund_open_fund_info_em`.

Live premium/discount (needs a same-moment price+IOPV pair, not history) is computed
separately in fund_analysis.py, not stored here.
"""
import time
from datetime import datetime, timezone
from typing import Callable, TypeVar

import akshare as ak
import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Fund, FundNav

T = TypeVar("T")


def _retry(func: Callable[[], T], attempts: int = 5, delay: float = 4.0) -> T:
    """Eastmoney's history endpoints (behind AKShare) intermittently reset the connection
    under light rate-limiting — retry a few times before giving up."""
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except Exception:
            if attempt == attempts:
                raise
            time.sleep(delay)
    raise AssertionError("unreachable")

FUND_TYPE_ETF = "ETF"
FUND_TYPE_LOF = "LOF"
FUND_TYPE_OTC = "OTC"

_fund_name_cache: pd.DataFrame | None = None


def _fund_name_table() -> pd.DataFrame:
    """`fund_name_em` full fund directory, cached for the life of the process."""
    global _fund_name_cache
    if _fund_name_cache is None:
        _fund_name_cache = ak.fund_name_em()
    return _fund_name_cache


def detect_fund_type(code: str) -> str:
    code = code.strip()
    if code[:2] in ("15", "51", "56", "58"):
        return FUND_TYPE_ETF
    if code[:2] in ("16", "50"):
        return FUND_TYPE_LOF
    return FUND_TYPE_OTC


def get_fund_name(code: str) -> str:
    df = _fund_name_table()
    row = df[df["基金代码"] == code]
    return str(row.iloc[0]["基金简称"]) if not row.empty else code


def fetch_etf_history(code: str, start: str, end: str, fund_type: str) -> pd.DataFrame:
    """ETF/LOF daily close price -> DataFrame[nav_date, close]."""
    hist_fn = ak.fund_lof_hist_em if fund_type == FUND_TYPE_LOF else ak.fund_etf_hist_em
    raw = _retry(lambda: hist_fn(symbol=code, period="daily", start_date=start, end_date=end, adjust=""))
    if raw.empty:
        return pd.DataFrame(columns=["nav_date", "close"])
    df = raw.rename(columns={"日期": "nav_date", "收盘": "close"})[["nav_date", "close"]]
    df["nav_date"] = pd.to_datetime(df["nav_date"]).dt.date
    return df


def fetch_otc_history(code: str, start: str, end: str) -> pd.DataFrame:
    """OTC daily nav/acc_nav -> DataFrame[nav_date, nav, acc_nav]. `start`/`end` are ISO dates."""
    df_unit = _retry(lambda: ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势"))
    df_acc = _retry(lambda: ak.fund_open_fund_info_em(symbol=code, indicator="累计净值走势"))
    df_unit = df_unit.rename(columns={"净值日期": "nav_date", "单位净值": "nav"})[["nav_date", "nav"]]
    df_acc = df_acc.rename(columns={"净值日期": "nav_date", "累计净值": "acc_nav"})[["nav_date", "acc_nav"]]
    df = pd.merge(df_unit, df_acc, on="nav_date", how="left")
    df["nav_date"] = pd.to_datetime(df["nav_date"])
    sd, ed = pd.to_datetime(start), pd.to_datetime(end)
    df = df[(df["nav_date"] >= sd) & (df["nav_date"] <= ed)]
    df["nav_date"] = df["nav_date"].dt.date
    return df.reset_index(drop=True)


async def ingest_fund(session: AsyncSession, code: str, start: str = "20230101") -> int:
    """Fetch full NAV/price history for `code` and upsert rows. Returns row count upserted."""
    code = code.strip()
    fund_type = detect_fund_type(code)
    name = get_fund_name(code)
    end = datetime.now().strftime("%Y%m%d")

    if fund_type in (FUND_TYPE_ETF, FUND_TYPE_LOF):
        df = fetch_etf_history(code, start, end, fund_type)
    else:
        iso_start = f"{start[0:4]}-{start[4:6]}-{start[6:8]}"
        iso_end = datetime.now().strftime("%Y-%m-%d")
        df = fetch_otc_history(code, iso_start, iso_end)

    if df.empty:
        return 0

    fund = (await session.execute(select(Fund).where(Fund.code == code))).scalar_one_or_none()
    if fund is None:
        fund = Fund(code=code, name=name, fund_type=fund_type)
        session.add(fund)
        await session.flush()

    rows = []
    for row in df.to_dict("records"):
        rows.append(
            {
                "fund_code": code,
                "nav_date": row["nav_date"],
                "nav": float(row["nav"]) if "nav" in row and pd.notna(row.get("nav")) else None,
                "acc_nav": float(row["acc_nav"]) if "acc_nav" in row and pd.notna(row.get("acc_nav")) else None,
                "close": float(row["close"]) if "close" in row and pd.notna(row.get("close")) else None,
            }
        )

    stmt = insert(FundNav).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["fund_code", "nav_date"],
        set_={"nav": stmt.excluded.nav, "acc_nav": stmt.excluded.acc_nav, "close": stmt.excluded.close},
    )
    await session.execute(stmt)

    fund.last_synced_at = datetime.now(timezone.utc)
    await session.commit()
    return len(rows)


async def load_nav_series(session: AsyncSession, code: str) -> pd.Series:
    """Stored nav (OTC) or close (ETF/LOF) series, indexed by date, for metrics."""
    fund = (await session.execute(select(Fund).where(Fund.code == code))).scalar_one_or_none()
    col = FundNav.close if fund and fund.fund_type in (FUND_TYPE_ETF, FUND_TYPE_LOF) else FundNav.nav
    rows = (
        await session.execute(
            select(FundNav.nav_date, col).where(FundNav.fund_code == code).order_by(FundNav.nav_date)
        )
    ).all()
    if not rows:
        return pd.Series(dtype=float)
    idx = pd.DatetimeIndex([r[0] for r in rows])
    return pd.Series([r[1] for r in rows], index=idx, name=code).dropna()
