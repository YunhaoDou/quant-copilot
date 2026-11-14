"""统一只读验收入口：不重启、不扫描、不下单、不调用AI；真实外网用例需显式选择。"""
import argparse
from datetime import datetime,timezone
import glob
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from time import monotonic

ROOT=Path(__file__).resolve().parents[2]


def run(with_network=False,skip_browser=False):
    steps=[];started=monotonic();env=os.environ.copy()
    if not env.get('PLAYWRIGHT_MODULE'):
        paths=glob.glob(str(Path.home()/'.npm/_npx/*/node_modules/playwright'))
        if paths:env['PLAYWRIGHT_MODULE']=max(paths,key=lambda p:Path(p).stat().st_mtime)
    checkpoint=ROOT/'backend/logs/account-verification-checkpoint.json'
    def step(name,args,cwd=ROOT,timeout=180):
        then=monotonic()
        try:
            result=subprocess.run([str(a) for a in args],cwd=cwd,env=env,capture_output=True,text=True,timeout=timeout)
            ok=result.returncode==0;detail=(result.stdout+'\n'+result.stderr)[-2000:]
        except subprocess.TimeoutExpired:ok=False;detail='验收步骤超时，未标记通过'
        # 报告只保留尾部，且不输出常见凭据形状；原始运行数据不进入Git。
        detail=re.sub(r'(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{25,})','[REDACTED]',detail)
        for key,value in env.items():
            if len(value)>=8 and any(s in key.upper() for s in ('TOKEN','SECRET','PASSWORD','API_KEY')):detail=detail.replace(value,'[REDACTED]')
        steps.append({'name':name,'ok':ok,'seconds':round(monotonic()-then,3),'detail':detail});print(name,'PASS' if ok else 'FAIL',flush=True);return ok
    python=sys.executable
    ready=step('api_ready',[python,ROOT/'scripts/wait-api.py','--timeout','30'],timeout=35)
    if ready:step('account_before',[python,ROOT/'scripts/account-checkpoint.py','capture','--database',ROOT/'backend/data/cycle/events.sqlite','--checkpoint',checkpoint])
    step('python_regression',[python,'-m','pytest','-q','--tb=short','-k','not test_get_premium_snapshot_real_etf'],ROOT/'backend',timeout=180)
    step('typescript',['npm','run','typecheck'],ROOT/'frontend',timeout=90)
    if ready:step('all_rows_parity',[python,ROOT/'backend/scripts/verify_data.py'],timeout=120)
    step('polling_policy',['node',ROOT/'frontend/test-polling-delay.cjs'])
    if ready and not skip_browser:
        for file in ['test-readonly-guard.cjs','test-performance-safety.cjs','test-workspace-consolidation.cjs','test-security-search.cjs','test-lazy-strategy-chart.cjs','test-market-polling.cjs','test-market-retry.cjs','test-service-connection.cjs','test-fund-source-failure.cjs','test-lazy-navigation.cjs','test-polling-visibility.cjs','test-kline-interaction.cjs','test-runtime-status.cjs','test-reference-placement.cjs']:
            step(file,['node',ROOT/'frontend'/file],timeout=120)
    if ready:
        step('benchmark_warm',[python,ROOT/'backend/scripts/benchmark_performance.py','--scenario','warm','--samples','12','--concurrency','4','--output',ROOT/'backend/logs/performance-verification.json'],timeout=600)
        step('account_after',[python,ROOT/'scripts/account-checkpoint.py','check','--database',ROOT/'backend/data/cycle/events.sqlite','--checkpoint',checkpoint])
    if with_network:step('external_iopv',[python,'-m','pytest','-q','--tb=short','tests/test_fund_analysis.py::test_get_premium_snapshot_real_etf'],ROOT/'backend')
    status='passed' if ready and all(s['ok'] for s in steps) and not skip_browser else 'partial' if skip_browser and all(s['ok'] for s in steps) else 'failed'
    report={'observed_at':datetime.now(timezone.utc).isoformat(),'status':status,'seconds':round(monotonic()-started,3),'browser_skipped':skip_browser,'external_iopv_checked':with_network,'independent_iopv':'未授权，按用户选择保留','steps':steps}
    target=ROOT/'backend/logs/verification-latest.json';target.parent.mkdir(parents=True,exist_ok=True);tmp=target.with_suffix('.tmp');tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2));tmp.replace(target)
    print(json.dumps({'status':status,'report':str(target),'steps':len(steps)},ensure_ascii=False));return status


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--with-network',action='store_true');parser.add_argument('--skip-browser',action='store_true');args=parser.parse_args();raise SystemExit(0 if run(args.with_network,args.skip_browser)=='passed' else 1)
