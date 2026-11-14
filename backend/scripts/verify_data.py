"""只读全量对照：快照版本一致后逐页比较，不把变化中的两版数据拼接。"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json
import time
import httpx
from app.cycle import read_api,security_search


def compare(client,builder,endpoint,field):
    for attempt in range(3):
        local=builder();first=client.get(endpoint);first.raise_for_status();payload=first.json()
        if payload['snapshot_version']!=local['snapshot_version']:time.sleep(1.1);continue
        expected=local[field];rows=[];version=payload['snapshot_version'];conflict=False
        for page in range(1,(len(expected)+49)//50+1):
            response=client.get(endpoint,params={'page':page,'version':version})
            if response.status_code==409:conflict=True;break
            response.raise_for_status();part=response.json()
            if part['snapshot_version']!=version:raise AssertionError('响应版本混合')
            rows+=part[field]
        if conflict:time.sleep(.2);continue
        if rows!=expected:raise AssertionError(endpoint+'字段或顺序不一致')
        return {'status':'ok','rows':len(rows),'version':version}
    raise RuntimeError(endpoint+'数据版本持续变化，未标记为通过；请在快照稳定后重试')


def run(base='http://127.0.0.1:8000'):
    with httpx.Client(base_url=base,trust_env=False,timeout=30) as client:
        result={'dividends':compare(client,read_api.dividend_model,'/dividends/stocks','stocks'),
                'screening':compare(client,read_api.screening_model,'/screening/results','results'),
                'securities':compare(client,security_search.master,'/tickers/search','rows')}
        old=client.get('/tickers');old.raise_for_status();old=old.json();master=security_search.master()
        if not isinstance(old,list) or [(r['symbol'],r['name'],r['asset_type']) for r in old]!=[(r['symbol'],r['name'],r['asset_type']) for r in master['rows']]:raise AssertionError('原完整名单契约不一致')
        result['legacy_tickers']={'status':'ok','rows':len(old)}
        return result


if __name__=='__main__':
    try:print(json.dumps(run(),ensure_ascii=False))
    except Exception as exc:print(json.dumps({'status':'error','reason':str(exc)},ensure_ascii=False));raise SystemExit(1)
