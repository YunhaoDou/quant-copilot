"""完整证券母池的轻量分页搜索；旧/tickers全量接口保持不变。"""
import re
from fastapi import APIRouter,HTTPException,Query,Request
from app.cycle import events,read_cache
router=APIRouter(prefix='/tickers',tags=['证券名单搜索'])


def master():
    stocks,stock_version=read_cache.document(events.DB_PATH,'all_a_universe')
    etfs,etf_version=read_cache.document(events.DB_PATH,'etf_universe')
    if not stocks:raise HTTPException(503,'官方全A股名单尚未就绪，请更新全市场数据')
    def build():
        suffix={'SH':'SS','SZ':'SZ','BJ':'BJ'}
        rows=[{k:row[k] for k in ('code','name','exchange')}|{'symbol':row['code']+'.'+suffix[row['exchange']],'market':'CN','asset_type':kind}
            for values,kind in ((stocks.get('stocks',[]),'STOCK'),((etfs or {}).get('rows',[]),'ETF')) for row in values]
        if len({r['symbol'] for r in rows})!=len(rows):raise HTTPException(503,'证券名单存在重复项，请核验来源，未静默丢弃记录')
        return {'rows':rows,'total':len(rows),'stock_total':len(stocks.get('stocks',[])),
            'etf_total':len(etfs.get('rows',[])) if etfs else None,
            'source':{'stocks':stocks.get('source'),'etfs':(etfs or {}).get('source')},
            'source_updated_at':{'stocks':stocks.get('updatedAt') or stocks.get('updated_at'),'etfs':(etfs or {}).get('updated_at')},
            'notes':[] if etfs else ['ETF名单尚未就绪，ETF覆盖未知，当前只展示已核实股票名单']}
    return read_cache.model('security-master',(str(events.DB_PATH),stock_version,etf_version),build)


def qualified(value):
    if not re.fullmatch(r'(?:SH|SZ|BJ)\d{6}|\d{6}\.(?:SH|SS|SZ|BJ)',value.upper()):return None
    from app.cycle.market import normalize_symbol
    return normalize_symbol(value)


@router.get('/search')
def search(request:Request,query:str=Query('',max_length=100),page:int=Query(1,ge=1),page_size:int=Query(50,ge=1,le=200),asset_type:str='all',selected:str=Query('',max_length=30),version:str|None=None):
    if asset_type not in ('all','STOCK','ETF'):raise HTTPException(422,'未知证券类型')
    model=read_cache.versioned('security-master',master(),version)
    q=query.strip().casefold();symbol=qualified(q)
    def match(row):
        return (asset_type=='all' or row['asset_type']==asset_type) and (not q or
            (row['exchange'].lower()+row['code']==symbol if symbol else q in row['code'] or q in row['name'].casefold() or q in row['symbol'].casefold()))
    rows=[r for r in model['rows'] if match(r)]
    chosen=qualified(selected)
    selected_row=next((r for r in model['rows'] if selected in (r['symbol'],r['code']) or chosen==r['exchange'].lower()+r['code']),None) if selected else None
    data={k:v for k,v in model.items() if k!='rows'}
    data.update(rows=rows[(page-1)*page_size:page*page_size],matched=len(rows),page=page,page_size=page_size,selected=selected_row)
    return read_cache.response(data,request,('security-search',model['snapshot_version'],query,page,page_size,asset_type,selected))
