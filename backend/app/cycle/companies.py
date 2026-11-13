"""按A股代码识别公司；客观行情与已实施分红独立标注来源。"""
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException
import httpx

from app.cycle.market import fetch_quotes, normalize_symbol
from app.cycle.dividends import build_dividends

router = APIRouter(prefix="/companies", tags=["公司识别"])


def stock_code(value):
    symbol = normalize_symbol(value)
    code = symbol[2:]
    expected = "sh" if code.startswith("6") else "sz" if code.startswith(("0", "3")) else "bj" if code.startswith(("4", "8", "92")) else None
    if expected is None or symbol[:2] != expected or (expected == "sh" and not code.startswith(("600", "601", "603", "605", "688", "689"))) or (expected == "sz" and not code.startswith(("000", "001", "002", "003", "300", "301", "302"))):
        raise ValueError("请输入A股公司股票代码，不支持指数或基金代码")
    return code


def dividend_facts(code, as_of, price, client):
    response = client.get("https://datacenter-web.eastmoney.com/api/data/v1/get", params={"reportName":"RPT_SHAREBONUS_DET", "columns":"SECURITY_CODE,ASSIGN_PROGRESS,EX_DIVIDEND_DATE,PRETAX_BONUS_RMB,REPORT_DATE,BONUS_IT_RATIO", "filter":f'(SECURITY_CODE="{code}")(ASSIGN_PROGRESS="实施分配")(EX_DIVIDEND_DATE>=\'{(date.fromisoformat(as_of)-timedelta(days=366*12)).isoformat()}\')(EX_DIVIDEND_DATE<=\'{as_of}\')', "pageSize":500, "pageNumber":1, "source":"WEB", "client":"WEB"})
    response.raise_for_status()
    payload = response.json()
    result = payload.get("result")
    if not payload.get("success") or not result or len(result.get("data") or []) != int(result.get("count", -1)):
        raise ValueError("分红数据未完整返回")
    rows = result["data"]
    if any(str(r.get("SECURITY_CODE")).zfill(6) != code for r in rows):
        raise ValueError("分红代码不匹配")
    values = build_dividends(rows, as_of).get(code)
    cash = values["cashPerShare"] if values else 0
    changed = values["shareChange"] if values else False
    return dict(cashPerShare=None if changed else cash, dividendYield=None if changed else cash/price*100,
        consecutiveYears=values["consecutiveYears"] if values else 0, asOf=as_of, source="东方财富已实施分红 / 腾讯报价",
        note="近12个月存在送转，每股口径待核实" if changed else "过去365天已实施税前每股派现 / 当前报价；不承诺未来分红", verified=not changed)


def identify(value):
    code = stock_code(value)
    quotes = fetch_quotes([code])
    quote = next((q for q in quotes["quotes"] if q["code"] == code), None)
    if not quote or quote["price"] is None or quote["price"] <= 0:
        raise ValueError("未识别到有效A股报价，请检查代码；未创建空白公司")
    as_of = quote["quote_time"][:10]
    dividend = dict(cashPerShare=None,dividendYield=None,asOf=as_of,source="东方财富已实施分红",note="暂未取得完整分红记录，股息率未知",verified=False)
    industry = None
    warnings = []
    with httpx.Client(trust_env=False,timeout=8,headers={"Referer":"https://quote.eastmoney.com/"}) as client:
        try:
            dividend = dividend_facts(code, as_of, quote["price"], client)
        except Exception:
            warnings.append("分红来源暂不可用；名称与行情识别不受影响，股息率不补造")
        try:
            response = client.get("https://push2.eastmoney.com/api/qt/ulist.np/get",params={"secids":("1." if quote["symbol"].startswith("sh") else "0." if quote["symbol"].startswith("sz") else "0.")+code,"fields":"f12,f100","fltt":2})
            response.raise_for_status()
            rows = (response.json().get("data") or {}).get("diff") or []
            if isinstance(rows,dict):
                rows=list(rows.values())
            if rows and rows[0].get("f12")==code and isinstance(rows[0].get("f100"),str) and rows[0]["f100"] not in ("", "-"):
                industry=rows[0]["f100"]
        except Exception:
            pass
    return dict(code=code,name=quote["name"],symbol=quote["symbol"],industry=industry,industrySource="东方财富行业分类" if industry else None,
        quote=quote,quoteSource=quotes["provider"],fetchedAt=quotes["fetched_at"],dividend=dividend,warnings=warnings,quality=None)


@router.get("/{code}")
def company(code: str):
    try:
        return identify(code)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503,"公司识别行情源暂不可用，请重试；不会保存虚构信息") from exc
