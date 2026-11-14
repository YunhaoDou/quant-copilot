"""只读性能基准：固定请求组合，记录负载、P50/P95、资源及覆盖，不触发扫描或交易。"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
import platform
import subprocess
from threading import Event,Thread
from time import perf_counter
import httpx

PATHS=('/health','/dividends/summary','/dividends/stocks','/screening/summary','/screening/results','/strategy-center/overview','/etfs?page=1','/tickers')


def source_identity():
    root=Path(__file__).resolve().parents[2]
    try:
        head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
        value=sha256(subprocess.check_output(['git','diff','HEAD','--','.'],cwd=root))
        paths=subprocess.check_output(['git','ls-files','--others','--exclude-standard','-z'],cwd=root).decode().split('\0')
        for path in sorted(p for p in paths if p):
            file=root/path
            if file.is_file():value.update(path.encode());value.update(file.read_bytes())
        return {'git_head':head,'working_copy_sha256':value.hexdigest()}
    except (OSError,subprocess.SubprocessError):return {'git_head':None,'working_copy_sha256':None}


def percentile(values,p):
    rows=sorted(values)
    if not rows:return None
    index=(len(rows)-1)*p;lo=int(index);hi=min(lo+1,len(rows)-1)
    return round(rows[lo]+(rows[hi]-rows[lo])*(index-lo),3)


def distribution(rows):
    good=[r for r in rows if r['ok']];times=[r['ms'] for r in good]
    return {'requests':len(rows),'successes':len(good),'errors':len(rows)-len(good),
        'p50_ms':percentile(times,.5),'p95_ms':percentile(times,.95),'max_ms':max(times) if times else None,
        'decoded_bytes':sorted({r['decoded_bytes'] for r in good}),'wire_bytes':sorted({r['wire_bytes'] for r in good if r['wire_bytes'] is not None})}


def evidence(client):
    def get(path):
        response=client.get(path);response.raise_for_status();return response.json()
    dividend=get('/dividends/summary');etf=get('/etfs?page=1');strategies=get('/strategy-center/overview');tickers=get('/tickers')
    active=dividend.get('status')=='running' or etf.get('progress',{}).get('status')=='running' or bool(strategies.get('refresh',{}).get('running'))
    symbols=[r['symbol'] for r in tickers]
    return {'stocks':strategies.get('market_scan',{}).get('total',0),'dividend_snapshot_rows':dividend['total'],'etfs':etf['total'],'tickers':len(tickers),'unique_tickers':len(set(symbols)),
        'strategies':len(strategies['strategies']),'dividend_version':dividend.get('snapshot_version'),
        'background_scan_active':active,'scan_states':{'dividends':dividend.get('status'),'etfs':etf.get('progress',{}),'strategies':strategies.get('refresh',{})},
        'source':dividend.get('source'),'data_date':dividend.get('tradeDate')}


def run(base,scenario,samples,concurrency):
    if samples<2 or concurrency<1:raise ValueError('样本数至少2，并发至少1')
    client=httpx.Client(base_url=base,trust_env=False,timeout=20,limits=httpx.Limits(max_connections=concurrency+2))
    try:
        live=client.get('/health/live');live.raise_for_status();live=live.json()
        if scenario=='cold' and (live.get('uptime_seconds') is None or live['uptime_seconds']>60):raise ValueError('cold模式要求新后端启动60秒以内；本工具不会擅自重启服务')
        before=evidence(client)
        if scenario=='background' and not before['background_scan_active']:raise ValueError('当前没有确认的扫描任务，不能标为后台扫描场景')
        if scenario=='warm':
            for path in PATHS:client.get(path).raise_for_status()
        stop=Event();resources=[]
        def sample_resources():
            while not stop.is_set():
                try:
                    output=subprocess.check_output(['ps','-p',str(live['pid']),'-o','%cpu=,rss='],text=True).split()
                    resources.append({'cpu_percent':float(output[0]),'rss_mb':round(int(output[1])/1024,2)})
                except (KeyError,ValueError,IndexError,subprocess.SubprocessError):pass
                stop.wait(.25)
        sampler=Thread(target=sample_resources,daemon=True);sampler.start()
        def request(path):
            started=perf_counter()
            try:
                response=client.get(path);response.raise_for_status()
                return {'path':path,'ok':True,'status':response.status_code,'ms':round((perf_counter()-started)*1000,3),
                    'decoded_bytes':len(response.content),'wire_bytes':int(response.headers['content-length']) if 'content-length' in response.headers else None}
            except Exception as exc:return {'path':path,'ok':False,'ms':round((perf_counter()-started)*1000,3),'error':type(exc).__name__}
        try:
            # 每轮固定同一组合；等整轮结束再开始下一轮，不无限堆积请求。
            rows=[]
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                for _ in range(samples):rows.extend(pool.map(request,PATHS))
        finally:stop.set();sampler.join(timeout=2)
        after=evidence(client)
        checks={'all_requests_succeeded':all(r['ok'] for r in rows),'coverage_matches':after['tickers']==after['unique_tickers']==after['stocks']+after['etfs'],
            'strategy_count_preserved':before['strategies']==after['strategies'],
            'snapshot_changed_during_run':before['dividend_version']!=after['dividend_version']}
        return {'schema_version':1,'observed_at':datetime.now(timezone.utc).isoformat(),'scenario':scenario,
            'cold_definition':'重启后60秒内开始，证据核验本身也会读取和预热部分接口；不是所有请求均为冷缓存',
            'environment':{'platform':platform.platform(),'python':platform.python_version(),'source':source_identity(),'external_load_controlled':False,'pid':live.get('pid'),'uptime_at_start':live.get('uptime_seconds')},
            'configuration':{'samples_per_endpoint':samples,'concurrency':concurrency,'paths':PATHS,'warmup_rounds':1 if scenario=='warm' else 0},
            'endpoints':{p:distribution([r for r in rows if r['path']==p]) for p in PATHS},'checks':checks,'before':before,'after':after,
            'resources':{'sample_count':len(resources),'cpu_p50_percent':percentile([r['cpu_percent'] for r in resources],.5),
                'cpu_p95_percent':percentile([r['cpu_percent'] for r in resources],.95),'rss_peak_mb':max((r['rss_mb'] for r in resources),default=None),
                'cpu_note':'ps提供进程CPU统计，不是机器总CPU；与具体负载一并解读'},
            'errors':[r for r in rows if not r['ok']]}
    finally:client.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--base',default='http://127.0.0.1:8000');parser.add_argument('--scenario',choices=['cold','warm','background'],default='warm');parser.add_argument('--samples',type=int,default=12);parser.add_argument('--concurrency',type=int,default=4);parser.add_argument('--output',default='logs/performance-latest.json');args=parser.parse_args()
    try:report=run(args.base,args.scenario,args.samples,args.concurrency)
    except Exception as exc:print(json.dumps({'status':'error','reason':str(exc)},ensure_ascii=False));raise SystemExit(1)
    target=Path(args.output);target.parent.mkdir(parents=True,exist_ok=True);tmp=target.with_suffix('.tmp');tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2));tmp.replace(target)
    print(json.dumps({'output':str(target.resolve()),'checks':report['checks'],'endpoints':report['endpoints'],'resources':report['resources']},ensure_ascii=False))
    raise SystemExit(0 if all(report['checks'][k] for k in ('all_requests_succeeded','coverage_matches','strategy_count_preserved')) else 1)
