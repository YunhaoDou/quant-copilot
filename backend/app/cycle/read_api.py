"""市场与策略的只读查询模型，旧全量接口继续兼容。"""
from collections import Counter
import copy
import json
from fastapi import APIRouter,HTTPException,Query,Request
from app.cycle import read_cache
from app.cycle.engine import load_config
router=APIRouter(tags=["轻量查询与版本快照"])


def dividend_model():
    from app.cycle import dividends
    raw,version=read_cache.document(dividends.DB_PATH,"board")
    cfg=load_config()
    if raw:cfg.update({k:v for k,v in raw.get("config",{}).items() if k=="dividend_min_fcf_cover"})
    key=(str(dividends.DB_PATH),version,json.dumps(cfg,sort_keys=True))
    def build():
        data=copy.deepcopy(raw) if raw else dict(stocks=[],strategyVersion=0,failures=[],notes=[])
        if data.get("strategyVersion",0)<4:data.update(stocks=[],legacy_snapshot=True)
        else:
            for row in data["stocks"]:row["screening"]=dividends.screen_candidate(row,data.get("benchmark"),cfg)
        rows=data["stocks"]
        data["categories"]=sorted({r["category"] for r in rows})
        data["industries"]={c:sorted({r["sector"] for r in rows if c=="全部" or r["category"]==c}) for c in ["全部",*data["categories"]]}
        data["passing_count"]=sum(r.get("screening",{}).get("status")=="pass" for r in rows)
        return data
    return read_cache.model("dividends",key,build)


def dividend_progress():
    from app.cycle import dividends
    with dividends._lock:
        state={k:v for k,v in dividends._state.items() if k in ("status","progress","checked","scanned","error")}
    # 刚重启时加载已保存元数据，不重算证券。
    if state.get("status")=="idle":
        raw,_=read_cache.document(dividends.DB_PATH,"board")
        if raw:state.update({k:raw[k] for k in state if k in raw})
    return state


@router.get("/dividends/summary")
def dividend_summary(request:Request):
    m=dividend_model();state=dividend_progress()
    data={k:m.get(k) for k in ("snapshot_version","strategyVersion","tradeDate","updatedAt","scanned","preselected","checked","source","benchmark","notes")}
    data.update(state,total=len(m["stocks"]),passing_count=m["passing_count"],failure_count=len(m.get("failures",[])))
    return read_cache.response(data,request)


@router.get("/dividends/stocks")
def dividend_page(request:Request,page:int=Query(1,ge=1),page_size:int=Query(50,ge=1,le=200),query:str=Query("",max_length=100),category:str="全部",sector:str="全部",only_low:bool=False,screen:str="all",version:str|None=None,selected:str=""):
    if screen not in ("all","pass","fail","unknown","manual","supported"):raise HTTPException(422,"未知筛选状态")
    m=read_cache.versioned("dividends",dividend_model(),version)
    def match(r):
        return (not query or query in r["code"] or query in r["name"]) and (category=="全部" or r["category"]==category) and (sector=="全部" or r["sector"]==sector) and (not only_low or r.get("signal")=="stage") and (screen=="all" or (r.get("quality",{}).get("status")=="supported" if screen=="supported" else r.get("screening",{}).get("status")==screen))
    rows=[r for r in m["stocks"] if match(r)];known=[r["dividendYield"] for r in rows if r.get("dividendYield") is not None]
    data={k:v for k,v in m.items() if k not in ("stocks","failures","industries")}
    data.update(stocks=rows[(page-1)*page_size:page*page_size],selected_stock=next((r for r in rows if r["code"]==selected),None),matched=len(rows),total=len(m["stocks"]),page=page,page_size=page_size,average_yield=sum(known)/len(known) if known else None,industries=m["industries"].get(category,[]),failure_count=len(m.get("failures",[])))
    key=("div-page",m["snapshot_version"],page,page_size,query,category,sector,only_low,screen,selected)
    return read_cache.response(data,request,key)


@router.get("/dividends/stocks/{code}")
def dividend_detail(code:str,request:Request,version:str|None=None):
    m=read_cache.versioned("dividends",dividend_model(),version);row=next((r for r in m["stocks"] if r["code"]==code),None)
    if row is None:raise HTTPException(404,"快照没有该股票")
    return read_cache.response(dict(snapshot_version=m["snapshot_version"],stock=row),request,("div-detail",m["snapshot_version"],code))


@router.get("/dividends/failures")
def dividend_failures(request:Request,page:int=Query(1,ge=1),page_size:int=Query(50,ge=1,le=200),version:str|None=None):
    m=read_cache.versioned("dividends",dividend_model(),version);rows=m.get("failures",[])
    return read_cache.response(dict(snapshot_version=m["snapshot_version"],rows=rows[(page-1)*page_size:page*page_size],total=len(rows),page=page),request,("div-errors",m["snapshot_version"],page,page_size))


def legacy_dividends(request):
    m=dividend_model();data={k:v for k,v in m.items() if k not in ("snapshot_version","categories","industries","passing_count")};state=dividend_progress();data.update(state)
    if m.get("legacy_snapshot") and state.get("status")!="running":data.update(status="needs_refresh",progress="旧快照存在候选数量限制，请重新执行全A股深入核验")
    return read_cache.response(data,request,("div-legacy",m["snapshot_version"],tuple(sorted(state.items()))))


def screening_model():
    from app.cycle import events,full_market
    raw,version=read_cache.document(events.DB_PATH,"full_stock_screening")
    return read_cache.model("screening",(str(events.DB_PATH),version),lambda:copy.deepcopy(raw) if raw else dict(results=[],universe_size=0,scored=0,unknown=0,scope="all-a",status=full_market.state["status"]))


def screening_state():
    m=screening_model();data={k:v for k,v in m.items() if k!="results"};state=dividend_progress()
    if state.get("status") in ("running","error"):data.update(status=state["status"],progress=state.get("progress"),checked=state.get("checked",0))
    return data


@router.get("/screening/summary")
def screening_summary(request:Request):return read_cache.response(screening_state(),request)


@router.get("/screening/results")
def screening_page(request:Request,page:int=Query(1,ge=1),page_size:int=Query(50,ge=1,le=200),query:str=Query("",max_length=100),version:str|None=None):
    m=read_cache.versioned("screening",screening_model(),version)
    rows=[r for r in m["results"] if not query or query in r["symbol"] or query in r.get("name","")]
    data={k:v for k,v in m.items() if k!="results"};data.update(results=rows[(page-1)*page_size:page*page_size],matched=len(rows),page=page,page_size=page_size)
    return read_cache.response(data,request,("screen-page",m["snapshot_version"],page,page_size,query))


@router.post("/screening/refresh",status_code=202)
def screening_refresh():
    from app.cycle.dividends import start_scan
    return start_scan()


def legacy_screening(request):
    m=screening_model();state=screening_state();data={**m,**state};data.pop("snapshot_version",None)
    return read_cache.response(data,request,("screen-legacy",m["snapshot_version"],json.dumps(state,sort_keys=True)))


@router.get("/strategy-center/overview")
def strategy_overview(request:Request,detail_id:str|None=None):
    from app.cycle.strategy_center import catalog
    data=catalog()
    for spec in data["strategies"]:
        a=spec.get("account")
        if not a:continue
        if spec["id"]==detail_id and spec["id"] not in ("leader-rebound","trend-leader-band","shibor-rotation"):
            # 独立的候选分页接口已包含完整核验，主账户不再重复捎带候选。
            spec["account"]={k:v for k,v in a.items() if k not in ("candidates",)}
        else:
            spec["account"]={k:v for k,v in a.items() if k in ("status","capital","cash","equity","peak","created_at","position","positions","pending","rules")}
    return read_cache.response(data,request)
