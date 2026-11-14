#!/usr/bin/env python3
"""只读就绪等待；HTTP成功但依赖降级时不得误报可用。"""
import argparse
import json
import time
from urllib.request import build_opener,ProxyHandler


def wait_ready(url,timeout=60,interval=.5,previous_pid=None,elapsed_origin=None):
    start=elapsed_origin if elapsed_origin is not None else time.monotonic();last='尚未连接';opener=build_opener(ProxyHandler({}))
    while time.monotonic()-start<timeout:
        try:
            remaining=timeout-(time.monotonic()-start)
            with opener.open(url,timeout=max(.05,min(2,remaining))) as response:
                body=json.load(response)
            if body.get('status')=='ok':
                if previous_pid:
                    with opener.open(url.rstrip('/')+'/live',timeout=max(.05,min(2,timeout-(time.monotonic()-start)))) as response:live=json.load(response)
                    if not live.get('pid') or str(live['pid'])==str(previous_pid):
                        last='等待新进程就绪';time.sleep(interval);continue
                return {'status':'ok','elapsed_seconds':round(time.monotonic()-start,3)}
            last='依赖未就绪'
        except Exception as exc:last=type(exc).__name__
        time.sleep(min(interval,max(0,timeout-(time.monotonic()-start))))
    return {'status':'timeout','elapsed_seconds':round(time.monotonic()-start,3),'reason':last}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--url',default='http://127.0.0.1:8000/health');parser.add_argument('--timeout',type=float,default=60)
    parser.add_argument('--previous-pid');parser.add_argument('--elapsed-origin',type=float);args=parser.parse_args();result=wait_ready(args.url,args.timeout,previous_pid=args.previous_pid,elapsed_origin=args.elapsed_origin);print(json.dumps(result,ensure_ascii=False));raise SystemExit(0 if result['status']=='ok' else 1)
