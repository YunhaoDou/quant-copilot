"""红利筛选使用同一财年的已实施派息与年报数据。"""
from datetime import date

import httpx

from app.cycle.live import number

DATA_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
REPORTS = {
    "income": ("RPT_DMSK_FN_INCOME", "PARENT_NETPROFIT,DEDUCT_PARENT_NETPROFIT"),
    "cash": ("RPT_DMSK_FN_CASHFLOW", "NETCASH_OPERATE,CONSTRUCT_LONG_ASSET"),
    "balance": ("RPT_DMSK_FN_BALANCE", "TOTAL_ASSETS,TOTAL_LIABILITIES,MONETARYFUNDS"),
}
QUALITY_ORDER = {"supported": 0, "review": 1, "financial": 2, "unknown": 3, "risk": 4}


def annual_statements(client, codes, as_of, config):
    """按小批次读取候选年报，部分接口失败时保留可验证字段。"""
    results = {key: {} for key in REPORTS}
    errors = []
    year = date.fromisoformat(as_of).year
    years = range(year - config["dividend_financial_years"] - 1, year)
    periods = ",".join(f"'{y}-12-31'" for y in years)
    size = config["dividend_financial_batch_size"]
    for offset in range(0, len(codes), size):
        batch = codes[offset:offset + size]
        securities = ",".join(f'"{code}"' for code in batch)
        for key, (report, fields) in REPORTS.items():
            try:
                response = client.get(DATA_URL, params={
                    "reportName": report, "columns": f"SECURITY_CODE,REPORT_DATE,NOTICE_DATE,{fields}",
                    "filter": f"(SECURITY_CODE in ({securities}))(REPORT_DATE in ({periods}))",
                    "sortColumns": "REPORT_DATE", "sortTypes": "-1",
                    "pageSize": 500, "source": "WEB", "client": "WEB",
                })
                response.raise_for_status()
                payload = response.json()
                result = payload.get("result") or {}
                rows = result.get("data") or []
                if not payload.get("success") or result.get("count", 0) != len(rows):
                    raise ValueError("数据源未返回完整批次")
                for row in rows:
                    code = row.get("SECURITY_CODE")
                    period, notice = (row.get("REPORT_DATE") or "")[:10], (row.get("NOTICE_DATE") or "")[:10]
                    if code not in batch or not period.endswith("-12-31") or not notice or notice > as_of:
                        continue
                    lookup = (code, int(period[:4]))
                    current = results[key].get(lookup)
                    if not current or notice > current["NOTICE_DATE"][:10]:
                        results[key][lookup] = row
            except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError) as exc:
                errors.append(f"财报 {key} 批次 {batch[0]}：{str(exc)[:100]}")
    return results, errors


def assess_quality(stock, statements, config):
    financial = stock["category"] == "金融"
    years = sorted((year for code, year in statements["income"] if code == stock["code"]), reverse=True)
    annual_cash = stock.get("fiscalDistributions", {})
    year = years[0] if years else None
    income = statements["income"].get((stock["code"], year), {})
    balance = statements["balance"].get((stock["code"], year), {})
    cashflow = statements["cash"].get((stock["code"], year), {})
    cash = annual_cash.get(year)
    profit = number(income.get("PARENT_NETPROFIT"))
    deduct = number(income.get("DEDUCT_PARENT_NETPROFIT"))
    ocf = number(cashflow.get("NETCASH_OPERATE"))
    capex = number(cashflow.get("CONSTRUCT_LONG_ASSET"))
    assets = number(balance.get("TOTAL_ASSETS"))
    liabilities = number(balance.get("TOTAL_LIABILITIES"))
    fcf = ocf - capex if ocf is not None and capex is not None and capex >= 0 else None
    payout = 100 * cash / profit if cash is not None and profit is not None and profit > 0 else None
    cover = fcf / cash if fcf is not None and cash is not None and cash > 0 else None
    debt = 100 * liabilities / assets if assets and assets > 0 and liabilities is not None and liabilities >= 0 else None
    window = config["dividend_financial_years"]
    earnings = [number(statements["income"].get((stock["code"], y), {}).get("DEDUCT_PARENT_NETPROFIT")) for y in range(year, year-window, -1)] if year else []
    baseline = stock.get("historicalCashPerShare")
    inflated = bool(baseline and stock["cashPerShare"] > baseline * config["dividend_cash_spike_multiple"])
    flags = []
    if inflated:
        flags.append("近12月派息明显高于前三个完整除权年度中位数，核对特别分红或派息时点")
    if profit is not None and profit <= 0:
        flags.append("最新可见年报归母净利润非正")
    if payout is not None and payout > config["dividend_payout_limit_pct"]:
        flags.append("已实施派息估算超过同财年利润门槛")
    if not financial:
        if deduct is not None and deduct <= 0:
            flags.append("最新可见年报扣非归母净利润非正")
        if cover is not None and cover < config["dividend_min_fcf_cover"]:
            flags.append("同财年自由现金流未达到派息覆盖门槛")
        if len(earnings) == window and all(v is not None for v in earnings):
            if any(v <= 0 for v in earnings):
                flags.append("近三财年扣非利润曾非正")
            elif earnings[0] < earnings[1] * (1 - config["dividend_profit_drop_pct"] / 100):
                flags.append("最近财年扣非利润降幅超过门槛")
        if debt is not None and debt >= config["dividend_debt_review_pct"]:
            flags.append("资产负债率达到复核线，结合行业及债务期限判断")
    complete = payout is not None and all(v is not None for v in earnings) and cover is not None and debt is not None
    if flags:
        risk = (profit is not None and profit <= 0) or (payout is not None and payout > config["dividend_payout_limit_pct"])
        risk = risk or (not financial and ((cover is not None and cover < config["dividend_min_fcf_cover"]) or (deduct is not None and deduct <= 0)))
        status = "risk" if risk else "review"
    elif financial:
        status = "financial"
    else:
        status = "supported" if complete and baseline is not None else "unknown"
    return {
        "status": status, "fiscalYear": year, "noticeDate": (income.get("NOTICE_DATE") or "")[:10] or None,
        "payoutPct": payout,
        "ocfCover": ocf / cash if not financial and ocf is not None and cash else None,
        "cashProfitRatio": ocf / profit if not financial and ocf is not None and profit is not None and profit > 0 else None, "fcfCover": None if financial else cover,
        "debtPct": None if financial else debt, "operatingCash": None if financial else ocf,
        "monetaryFunds": None if financial else number(balance.get("MONETARYFUNDS")),
        "deductedProfits": earnings, "historicalYield": baseline / stock["price"] * 100 if baseline else None,
        "flags": flags, "financialIndustry": financial,
    }


def quality_order(stock):
    quality = stock["quality"]
    return (QUALITY_ORDER[quality["status"]], -(quality["historicalYield"] or 0),
            -stock["consecutiveYears"], -stock["dividendYield"], stock["code"])
