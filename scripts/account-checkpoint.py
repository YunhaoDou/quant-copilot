#!/usr/bin/env python3
"""重启前后只读核验账本；检查点仅保存摘要，不复制资金或持仓明文。"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

TABLES=(('research_strategy_accounts','strategy_id'),('strategy_sim','id'),('trend_forward_account','id'),('shibor_sim','id'))


def digest(value):return sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def accounts(path):
    if not Path(path).exists():return {}
    db=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)
    try:
        db.execute('PRAGMA query_only=ON');result={}
        for table,key in TABLES:
            if db.execute('SELECT 1 FROM sqlite_master WHERE name=?',(table,)).fetchone():
                result.update({table+':'+str(row[0]):json.loads(row[1]) for row in db.execute(f'SELECT {key},payload FROM {table}')})
        return result
    finally:db.close()


def checkpoint(rows):
    return {name:{'metadata_hash':digest({k:a.get(k) for k in ('created_at','capital','rules')}),'trades_count':len(a.get('trades',[])),'trades_hash':digest(a.get('trades',[]))} for name,a in rows.items()}


def compare(before,rows):
    errors=[]
    for name,old in before.items():
        if name not in rows:errors.append(name+':missing');continue
        current=checkpoint({name:rows[name]})[name]
        if old['metadata_hash']!=current['metadata_hash']:errors.append(name+':metadata_changed')
        if old['trades_hash']!=digest(rows[name].get('trades',[])[:old['trades_count']]):errors.append(name+':history_changed')
    return {'status':'ok' if not errors else 'error','accounts_checked':len(before),'errors':errors,
        'new_trades':sum(max(0,len(rows.get(n,{}).get('trades',[]))-r['trades_count']) for n,r in before.items())}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['capture','check']);parser.add_argument('--database',required=True);parser.add_argument('--checkpoint',required=True);args=parser.parse_args();rows=accounts(args.database);target=Path(args.checkpoint)
    if args.action=='capture':
        target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(checkpoint(rows)));print(json.dumps({'status':'captured','accounts':len(rows)}))
    else:
        result=compare(json.loads(target.read_text()),rows);print(json.dumps(result));raise SystemExit(0 if result['status']=='ok' else 1)
