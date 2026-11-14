"""在线重新下载官方完整股票、ETF名单，仅核对不覆盖快照；失败不得计为通过。"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import json
from app.cycle import events,read_cache
from app.cycle.official_master import official_master
from app.cycle.etf_universe import official_etfs


def compare(saved,online):
    local={(r['exchange'],r['code']):r['name'] for r in saved}
    fresh={(r['exchange'],r['code']):r['name'] for r in online}
    if len(local)!=len(saved) or len(fresh)!=len(online):raise ValueError('名单含重复证券')
    key=lambda rows:[exchange+code for exchange,code in sorted(rows)]
    return {'ok':local==fresh,'saved_total':len(saved),'official_total':len(online),
            'newly_listed':key(fresh.keys()-local.keys()),'no_longer_listed':key(local.keys()-fresh.keys()),
            'name_changed':key(k for k in local.keys()&fresh.keys() if local[k]!=fresh[k])}


def run():
    jobs=[('stocks','all_a_universe','stocks',official_master),('etfs','etf_universe','rows',official_etfs)]
    result={'observed_at':datetime.now(timezone.utc).isoformat(),'read_only':True,'sources':{}}
    with ThreadPoolExecutor(2) as pool:
        futures={name:pool.submit(fetch) for name,_,_,fetch in jobs}
        for name,table,field,_ in jobs:
            try:
                online=futures[name].result();saved,version=read_cache.document(events.DB_PATH,table)
                if not saved:raise ValueError('本地完整快照不存在')
                result['sources'][name]={**compare(saved[field],online),'saved_version':version}
            except Exception as exc:result['sources'][name]={'ok':False,'error_type':type(exc).__name__}
    result['status']='passed' if all(r['ok'] for r in result['sources'].values()) else 'failed'
    return result


if __name__=='__main__':
    report=run();target=Path(__file__).resolve().parents[1]/'logs/verification-official-master.json'
    target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False));raise SystemExit(0 if report['status']=='passed' else 1)
