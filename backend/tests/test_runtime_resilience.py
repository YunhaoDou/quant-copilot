"""启动就绪、真实数据缺失与有限故障恢复的确定性回归，不请求外网。"""
import asyncio
from datetime import datetime,timezone
import importlib.util
from pathlib import Path
from threading import Thread,get_ident
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import httpx
import pandas as pd
import pytest
from app.services import fund_analysis as fund


def client_for(monkeypatch,handler):
    original=httpx.Client
    monkeypatch.setattr(fund.httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))


def quote(code='513330',price=1.12,iopv=1.0):
    return {'data':{'diff':[{'f12':code,'f14':'测试ETF','f2':price,'f441':iopv,'f124':1794546000}]}}


def test_iopv_fallback_is_same_provider_and_never_mixes_rows(monkeypatch):
    calls=[]
    def handler(request):
        calls.append(request.url.host)
        if len(calls)==1:raise httpx.RemoteProtocolError('disconnected')
        return httpx.Response(200,json=quote(),request=request)
    client_for(monkeypatch,handler)
    result=fund.get_premium_snapshot('513330','ETF')
    assert calls==['push2.eastmoney.com','82.push2.eastmoney.com']
    assert result.price==1.12 and result.iopv==1 and result.premium_rate==12
    from zoneinfo import ZoneInfo
    assert result.quote_time==datetime.fromtimestamp(1794546000,ZoneInfo('Asia/Shanghai')).isoformat()
    assert result.source_url.startswith('https://82.push2.eastmoney.com/')
    assert result.source_attempts[0]['status']=='connection_error' and result.source_attempts[-1]['status']=='ok'


def test_missing_iopv_is_unknown_without_substitution_or_more_requests(monkeypatch):
    calls=[]
    def handler(request):calls.append(request);return httpx.Response(200,json=quote(iopv='-'),request=request)
    client_for(monkeypatch,handler)
    assert fund.get_premium_snapshot('513330','ETF') is None and len(calls)==1


def test_rate_limit_stops_and_wrong_security_is_rejected(monkeypatch):
    calls=[]
    mode={'limited':True}
    def limited(request):
        calls.append(request)
        return httpx.Response(429,request=request) if mode['limited'] else httpx.Response(200,json=quote(code='510300'),request=request)
    client_for(monkeypatch,limited)
    with pytest.raises(fund.PremiumSourceError) as error:fund.get_premium_snapshot('513330','ETF')
    assert error.value.category=='rate_limited' and len(calls)==1
    mode['limited']=False
    with pytest.raises(fund.PremiumSourceError) as error:fund.get_premium_snapshot('513330','ETF')
    assert error.value.category=='code_mismatch' and len(error.value.attempts)==2


@pytest.mark.asyncio
async def test_source_failure_keeps_nav_metrics_and_runs_off_event_loop(monkeypatch):
    async def nav(*args):return pd.Series([1.,1.1],index=pd.date_range('2026-11-01',periods=2))
    monkeypatch.setattr(fund.fund_data,'load_nav_series',nav);thread=[];main=get_ident()
    def failure(*args):thread.append(get_ident());raise fund.PremiumSourceError('timeout',[])
    monkeypatch.setattr(fund,'get_premium_snapshot',failure)
    result=await fund.get_fund_analysis(None,'513330','ETF')
    assert result['metrics']['total_return']>0 and result['premium'] is None
    assert result['premium_status']['category']=='timeout' and thread[0]!=main


def test_wait_ready_rejects_http_success_with_degraded_dependencies():
    root=Path(__file__).resolve().parents[2]
    spec=importlib.util.spec_from_file_location('wait_api',root/'scripts/wait-api.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    class Handler(BaseHTTPRequestHandler):
        calls=0
        def do_GET(self):
            Handler.calls+=1;self.send_response(200);self.end_headers();self.wfile.write(json.dumps({'status':'degraded' if Handler.calls==1 else 'ok'}).encode())
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        result=module.wait_ready(f'http://127.0.0.1:{server.server_port}/health',timeout=1,interval=.01)
        assert result['status']=='ok' and Handler.calls==2
    finally:server.shutdown();server.server_close();thread.join()


def test_benchmark_percentiles_and_failures_are_not_counted_as_success():
    path=Path(__file__).resolve().parents[1]/'scripts/benchmark_performance.py'
    spec=importlib.util.spec_from_file_location('benchmark',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    result=module.distribution([{'ok':True,'ms':10,'decoded_bytes':99,'wire_bytes':50},{'ok':True,'ms':30,'decoded_bytes':99,'wire_bytes':50},{'ok':False,'ms':1}])
    assert result['requests']==3 and result['errors']==1 and result['p50_ms']==20 and result['p95_ms']==29


def test_restart_checkpoint_preserves_history_and_allows_new_trades():
    root=Path(__file__).resolve().parents[2]
    spec=importlib.util.spec_from_file_location('account_checkpoint',root/'scripts/account-checkpoint.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    import copy
    old={'one':{'created_at':'t','capital':100000,'rules':{'lot':100},'trades':[{'side':'buy','price':10}]}}
    before=module.checkpoint(old);now=copy.deepcopy(old);now['one']['trades'].append({'side':'sell','price':11})
    assert module.compare(before,now)['status']=='ok' and module.compare(before,now)['new_trades']==1
    now['one']['trades'][0]['price']=9
    assert module.compare(before,now)['status']=='error'


def test_api_import_does_not_preload_optional_backtest_runtime():
    import subprocess,sys
    backend=Path(__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,'-c','import app.main;import sys;assert "vectorbt" not in sys.modules'],cwd=backend,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
