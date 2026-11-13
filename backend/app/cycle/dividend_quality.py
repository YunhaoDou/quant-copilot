"""红利筛选使用同一财年的已实施派息与年报数据。"""
from app.cycle.live import number

DATA_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
REPORTS = {
    "income": ("RPT_DMSK_FN_INCOME", "PARENT_NETPROFIT,DEDUCT_PARENT_NETPROFIT"),
    "cash": ("RPT_DMSK_FN_CASHFLOW", "NETCASH_OPERATE,CONSTRUCT_LONG_ASSET"),
    "balance": ("RPT_DMSK_FN_BALANCE", "TOTAL_ASSETS,TOTAL_LIABILITIES,MONETARYFUNDS"),
}
QUALITY_ORDER = {"supported": 0, "review": 1, "financial": 2, "unknown": 3, "risk": 4}


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
        "deductedProfits": earnings, "historicalYield": baseline / stock["price"] * 100 if baseline and stock.get("price") and stock["price"] > 0 else None,
        "flags": flags, "financialIndustry": financial,
    }


def quality_order(stock):
    quality = stock["quality"]
    return (QUALITY_ORDER[quality["status"]], -(quality["historicalYield"] or 0),
            -stock["consecutiveYears"], -stock["dividendYield"], stock["code"])


def screen_candidate(stock, benchmark, config):
    """用扫描快照核验可量化的参考条件，保留未知项和财务红旗。"""
    quality = stock.get("quality") or {}
    historical = number(quality.get("historicalYield"))
    bond_yield = number((benchmark or {}).get("yieldPct"))
    spread = historical - bond_yield if historical is not None and bond_yield is not None else None
    checks = []

    def check(label, value, unit, lower_key, upper_key=None):
        value = number(value)
        lower = config[lower_key]
        upper = config[upper_key] if upper_key else None
        result = None if value is None else value >= lower and (upper is None or value <= upper)
        checks.append(dict(label=label, value=value, unit=unit, minimum=lower, maximum=upper, passed=result))

    check("近12月已实施股息率", stock.get("dividendYield"), "%", "dividend_screen_yield_min_pct", "dividend_screen_yield_max_pct")
    check("历史中位股息率减十年期国债", spread, "个百分点", "dividend_screen_spread_min_pp")
    check("连续派息", stock.get("consecutiveYears"), "年", "dividend_screen_min_years")
    check("同财年估算派息率", quality.get("payoutPct"), "%", "dividend_screen_payout_min_pct", "dividend_screen_payout_max_pct")
    check("经营现金流覆盖派息", quality.get("ocfCover"), "倍", "dividend_screen_ocf_cover_min")
    check("经营现金流 / 归母净利润", quality.get("cashProfitRatio"), "倍", "dividend_screen_cash_profit_min")
    check("自由现金流覆盖派息", quality.get("fcfCover"), "倍", "dividend_min_fcf_cover")
    tier = quality.get("status")
    if tier == "risk" or any(item["passed"] is False for item in checks):
        status = "fail"
    elif quality.get("financialIndustry"):
        status = "manual"
    elif any(item["passed"] is None for item in checks) or tier == "unknown":
        status = "unknown"
    elif tier != "supported":
        status = "manual"
    else:
        status = "pass"
    return {"status": status, "checks": checks}
