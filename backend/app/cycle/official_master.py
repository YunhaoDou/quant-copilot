"""沪深北交易所官方普通A股名单，核对分页总数并按代码去重。"""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import json
import re
import requests
import pandas as pd

UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"


def official_master():
    def sh(kind):
        r=requests.get("https://query.sse.com.cn/sseQuery/commonQuery.do",headers={"User-Agent":UA,"Referer":"https://www.sse.com.cn/assortment/stock/list/share/"},params={"STOCK_TYPE":kind,"sqlId":"COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L","COMPANY_STATUS":"2,4,5,7,8","type":"inParams","isPagination":"true","pageHelp.pageSize":"10000","pageHelp.pageNo":"1"},timeout=20)
        r.raise_for_status();p=r.json();rows=p["result"]
        if len(rows)!=int(p["pageHelp"]["total"]):raise ValueError("上交所名单未完整返回")
        return [dict(code=row["A_STOCK_CODE"],name=row["SEC_NAME_CN"],sector="待分类",exchange="SH",listed_date=row.get("LIST_DATE")) for row in rows]
    def sz():
        r=requests.get("https://www.szse.cn/api/report/ShowReport",params={"SHOWTYPE":"xlsx","CATALOGID":"1110","TABKEY":"tab1"},headers={"User-Agent":UA},timeout=20);r.raise_for_status()
        frame=pd.read_excel(BytesIO(r.content),dtype={"A股代码":str})
        rows=[dict(code=str(row["A股代码"]).split('.')[0].zfill(6),name=row["A股简称"],sector=str(row.get("所属行业") or "待分类"),exchange="SZ",listed_date=str(row.get("A股上市日期") or "")) for row in frame.to_dict("records")]
        if not rows:raise ValueError("深交所完整Excel名单为空")
        return rows
    def bj():
        def page(n):
            r=requests.post("https://www.bse.cn/nqxxController/nqxxCnzq.do",data={"page":str(n),"typejb":"T","xxfcbj[]":"2","xxzqdm":"","sortfield":"xxzqdm","sorttype":"asc"},headers={"User-Agent":UA},timeout=20);r.raise_for_status();s=r.text
            return json.loads(s[s.find('['):s.rfind(']')+1])[0]
        first=page(0);raw=list(first["content"])
        for n in range(1,first["totalPages"]):
            p=page(n)
            if p["totalElements"]!=first["totalElements"]:raise ValueError("北交所名单总数变化")
            raw.extend(p["content"])
        if len(raw)!=first["totalElements"]:raise ValueError("北交所名单未完整返回")
        return [dict(code=row["xxzqdm"],name=row["xxzqjc"],sector=row.get("xxhyzl") or "待分类",exchange="BJ",listed_date=row.get("fxssrq")) for row in raw]
    jobs=[lambda:sh("1"),lambda:sh("8"),sz,bj]
    with ThreadPoolExecutor(max_workers=4) as pool:
        parts=list(pool.map(lambda fn:fn(),jobs))
    rows=[row for part in parts for row in part]
    if not all(re.fullmatch(r"\d{6}",row["code"]) for row in rows) or len({r["code"] for r in rows})!=len(rows):raise ValueError("官方名单存在非法或重复代码")
    return rows
