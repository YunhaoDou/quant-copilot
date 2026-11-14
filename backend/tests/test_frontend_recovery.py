"""隔离端口验证生产前端启动失败自动恢复及并发复用，不触碰真实3000服务。"""
from pathlib import Path
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
import pytest


@pytest.fixture
def runtime(tmp_path):
    root=Path(__file__).resolve().parents[2];project=tmp_path/'project';scripts=project/'scripts';front=project/'frontend';logs=project/'backend/logs';bins=project/'bin'
    for path in [scripts,front/'scripts',front/'node_modules/next/dist/bin',logs,bins]:path.mkdir(parents=True,exist_ok=True)
    for name in ['frontend-service.sh','service-lock.sh']:shutil.copy(root/'scripts'/name,scripts/name)
    (front/'invest').write_text('original healthy frontend')
    for sha in ['oldhash','newhash']:
        dist=front/('.next-release-'+sha);dist.mkdir();(dist/'BUILD_ID').write_text('complete');(dist/'.quant-source-sha').write_text(sha)
    manifest={'dist':'.next-release-oldhash','previous':'','mode':'production','fingerprint':'oldhash'}
    (logs/'frontend-release.json').write_text(json.dumps(manifest))
    node=shutil.which('node')
    (bins/'node').write_text(f'''#!/bin/bash
if [ "$1" = "scripts/source-fingerprint.mjs" ];then printf '%s' "${{TEST_SHA:-newhash}}";exit 0;fi
if [ "$1" = "node_modules/next/dist/bin/next" ];then
    if [ "$QUANT_NEXT_DIST_DIR" = ".next-release-newhash" ];then exit 19;fi
    exec "{sys.executable}" -m http.server "${{!#}}" --bind 127.0.0.1 --directory "{front}"
fi
exec "{node}" "$@"
''')
    (bins/'node').chmod(0o755);(bins/'uname').write_text('#!/bin/bash\necho Linux\n');(bins/'uname').chmod(0o755)
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
    old=subprocess.Popen([sys.executable,'-m','http.server',str(port),'--bind','127.0.0.1','--directory',str(front)],cwd=front,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    (logs/'frontend.pid').write_text(str(old.pid))
    for _ in range(100):
        try:
            with urlopen(f'http://127.0.0.1:{port}/invest',timeout=.1):break
        except Exception:time.sleep(.02)
    else:raise AssertionError('fixture server unavailable')
    env={**os.environ,'PATH':str(bins)+os.pathsep+os.environ['PATH'],'QUANT_FRONTEND_PORT':str(port),'QUANT_FRONTEND_READY_SECONDS':'3','TEST_SHA':'newhash'}
    yield project,logs,port,old,env
    try:
        current=int((logs/'frontend.pid').read_text())
        if current>1 and current!=os.getpid():os.kill(current,signal.SIGTERM)
    except (OSError,ValueError):pass
    old.terminate();old.wait(timeout=5)


def test_failed_new_runtime_restores_old_build(runtime):
    project,logs,port,old,env=runtime;before=(logs/'frontend-release.json').read_bytes()
    result=subprocess.run(['bash',str(project/'scripts/frontend-service.sh')],env=env,capture_output=True,text=True,timeout=20)
    assert result.returncode!=0 and '已自动恢复原构建' in result.stderr,result.stdout+result.stderr
    with urlopen(f'http://127.0.0.1:{port}/invest',timeout=2) as r:assert r.read()==b'original healthy frontend'
    assert (logs/'frontend-release.json').read_bytes()==before
    assert int((logs/'frontend.pid').read_text())!=old.pid
    assert not (logs/'frontend-start.lock').exists()


def test_concurrent_starts_reuse_one_existing_process(runtime):
    project,logs,port,old,env=runtime;env['TEST_SHA']='oldhash';command=['bash',str(project/'scripts/frontend-service.sh')]
    jobs=[subprocess.Popen(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
    for job in jobs:
        out,err=job.communicate(timeout=20);assert job.returncode==0,out+err
    assert int((logs/'frontend.pid').read_text())==old.pid and old.poll() is None
    assert not (logs/'frontend-start.lock').exists()
