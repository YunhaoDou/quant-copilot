"""全A股母池与完整财报/分红读取；完整分页验证，不以红利资格截断。"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, date
import json
import time
from threading import Lock
import httpx
from app.cycle.live import TZ, number
from app.cycle.events import database, encode
from app.cycle.engine import load_config
from app.cycle.dividends import build_dividends, classify
from app.cycle.dividend_quality import REPORTS, DATA_URL, assess_quality
from app.cycle.dividend_benchmark import fetch_benchmark
from app.cycle.official_master import official_master

_lock=Lock()
state={"state":"尚未读取全A股", "total":0, "checked":0, "error":None}
MARKET_URL="https://push2.eastmoney.com/api/qt/clist/get"
MARKET_FS="m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"


def schema(db):
    db.execute("CREATE TABLE IF NOT EXISTS all_a_universe (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")


def saved():
    with database() as db:
        schema(db)
        row=db.execute("SELECT payload FROM all_a_universe WHERE id=1").fetchone()
    return json.loads(row[0]) if row else None


def pages(client,url,params,page_key,kind):
    """各页总数一致且收齐才返回；异常保留上次完整母池。"""
    cfg=load_config()
    def fetch(page):
        for attempt in range(3):
            try:
                node = url.replace("push2.eastmoney.com","82.push2.eastmoney.com") if attempt and kind=="market" else url
                r=client.get(node,params={**params,page_key:page});r.raise_for_status()
                p=r.json()
                break
            except (httpx.HTTPError,ValueError):
                if attempt==2:raise
                time.sleep(.5*(attempt+1))
        data=p.get("data") if kind=="market" else p.get("result")
        if not isinstance(data,dict):raise ValueError("全市场源未返回完整数据结构")
        rows=data.get("diff") if kind=="market" else data.get("data")
        rows=list(rows.values()) if isinstance(rows,dict) else rows
        count=data.get("total") if kind=="market" else data.get("count")
        if not isinstance(rows,list) or not isinstance(count,int):raise ValueError("全市场分页数量缺失")
        return rows,count
    first,total=fetch(1)
    size=params.get("pz",params.get("pageSize"))
    count=(total+size-1)//size
    if count>cfg["dividend_max_pages"]:raise ValueError("分页安全上限不足，拒绝声称全市场完成")
    rows=list(first)
    with ThreadPoolExecutor(max_workers=cfg["research_scan_workers"]) as pool:
        futures=[pool.submit(fetch,n) for n in range(2,count+1)]
        for f in as_completed(futures):
            more,reported=f.result()
            if reported!=total:raise ValueError("扫描期间全市场总数变化，须重试")
            rows.extend(more)
    if len(rows)!=total:raise ValueError("全市场分页未完整收齐")
    return rows


def refresh():
    if not _lock.acquire(blocking=False):raise ValueError("全A股母池正在更新")
    try:
        cfg=load_config();state.update(state="读取完整全A股名单",error=None,checked=0)
        with httpx.Client(trust_env=False,timeout=cfg["live_timeout_seconds"],headers={"Referer":"https://quote.eastmoney.com/","User-Agent":"Mozilla/5.0"}) as client:
            market=official_master()
            if not market:raise ValueError("官方全A股名单为空")
            now=datetime.now(TZ);as_of=now.date().isoformat()
            stocks=[]
            for row in market:
                sector=row.get("sector") or "待分类"
                stocks.append(dict(**row,category="金融" if "金融" in sector else classify(sector),marketCap=None,price=None,pe=None,pb=None,quoteTime=None))
            # 名单先发布，包含无分红、亏损、停牌与风险警示证券。证据缺失不放行交易。
            payload=dict(scope="all-a",tradeDate=as_of,updatedAt=now.isoformat(),source="沪深北交易所官方A股名单 / 东方财富年报与已实施分红",total=len(stocks),stocks=stocks,evidence_state="正在补齐财报与分红")
            with database() as db:
                schema(db);db.execute("INSERT OR REPLACE INTO all_a_universe VALUES(1,?)",(encode(payload),))
            state.update(state="读取全A股分红与财报",total=len(stocks))
            start=date.fromisoformat(as_of)-timedelta(days=366*cfg["dividend_lookback_years"])
            records=pages(client,DATA_URL,dict(reportName="RPT_SHAREBONUS_DET",columns="SECURITY_CODE,SECURITY_NAME_ABBR,ASSIGN_PROGRESS,EX_DIVIDEND_DATE,PRETAX_BONUS_RMB,REPORT_DATE,BONUS_IT_RATIO,BONUS_RATIO,IT_RATIO,TOTAL_SHARES",sortColumns="EX_DIVIDEND_DATE",sortTypes="-1",pageSize=cfg["dividend_page_size"],source="WEB",client="WEB",filter=f'(ASSIGN_PROGRESS="实施分配")(EX_DIVIDEND_DATE>=\'{start}\')(EX_DIVIDEND_DATE<=\'{as_of}\')'),"pageNumber","report")
            dividends=build_dividends(records,as_of)
            statements={key:{} for key in REPORTS};codes={s["code"] for s in stocks}
            years=range(now.year-cfg["dividend_financial_years"]-1,now.year)
            periods=",".join(f"'{year}-12-31'" for year in years)
            for key,(report,fields) in REPORTS.items():
                state.update(state="读取全A股年报："+key)
                rows=pages(client,DATA_URL,dict(reportName=report,columns="SECURITY_CODE,REPORT_DATE,NOTICE_DATE,"+fields+(",INDUSTRY_NAME" if key=="income" else ""),filter=f"(REPORT_DATE in ({periods}))(NOTICE_DATE<='{as_of}')",sortColumns="REPORT_DATE,SECURITY_CODE",sortTypes="-1,1",pageSize=cfg["dividend_page_size"],source="WEB",client="WEB"),"pageNumber","report")
                for row in rows:
                    code=row.get("SECURITY_CODE");period=(row.get("REPORT_DATE") or "")[:10];notice=(row.get("NOTICE_DATE") or "")[:10]
                    if code not in codes or not period.endswith("-12-31") or not notice or notice>as_of:continue
                    lookup=(code,int(period[:4]));previous=statements[key].get(lookup)
                    if not previous or notice>previous["NOTICE_DATE"][:10]:statements[key][lookup]=row
            try:benchmark=fetch_benchmark(client,as_of)
            except Exception:benchmark=None
        for stock in stocks:
            stock.update(dividends.get(stock["code"],dict(cashPerShare=0,consecutiveYears=0,historicalCashPerShare=None,fiscalDistributions={},shareChange=False)))
            visible=[(year,row) for (code,year),row in statements["income"].items() if code==stock["code"]]
            industry=max(visible,key=lambda item:item[0])[1].get("INDUSTRY_NAME") if visible else None
            if industry:
                stock["sector"]=industry
                stock["category"]="金融" if "金融" in industry else classify(industry)
            stock["quality"]=assess_quality(stock,statements,cfg)
            q=stock["quality"];profits=q.get("deductedProfits",[]);cash=q.get("cashProfitRatio");debt=q.get("debtPct")
            known=len(profits)==cfg["dividend_financial_years"] and all(v is not None for v in profits) and cash is not None and debt is not None
            if stock["sector"]=="待分类":known=False
            q["financialEvidenceStatus"]="financial" if q.get("financialIndustry") else "unknown" if not known else "supported" if all(v>0 for v in profits) and cash>=cfg["dividend_screen_cash_profit_min"] and debt<cfg["dividend_debt_review_pct"] else "risk"
            stock.pop("fiscalDistributions",None);stock.pop("dividendRecords",None)
        payload.update(stocks=stocks,benchmark=benchmark,evidence_state="财报与分红读取完成")
        with database() as db:db.execute("INSERT OR REPLACE INTO all_a_universe VALUES(1,?)",(encode(payload),))
        state.update(state="全A股母池与财务证据就绪",total=len(stocks),checked=len(stocks))
        return payload
    except Exception as exc:
        state.update(state="全A股读取失败",error=str(exc)[:200]);raise
    finally:_lock.release()
