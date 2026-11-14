"""公共行情资源预算：后台扫描有上限，交互与持仓读取保留容量。"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from threading import Condition
from time import monotonic

_background=ContextVar('market_background',default=False)
_held=ContextVar('market_held',default=frozenset())


class ResourceGate:
    def __init__(self,total=6,background=4):
        self.condition=Condition();self.total=total;self.background_limit=background
        self.active=0;self.background_active=0;self.waiting=0;self.foreground_waiting=0;self.requests=0;self.wait_seconds=0.

    def configure(self,total,background):
        if not 1<=background<total:raise ValueError('后台容量必须小于总容量')
        with self.condition:self.total=total;self.background_limit=background;self.condition.notify_all()

    @contextmanager
    def slot(self,background=False):
        start=monotonic()
        with self.condition:
            self.waiting+=1
            if not background:self.foreground_waiting+=1
            try:
                while self.active>=self.total or (background and (self.background_active>=self.background_limit or self.foreground_waiting)):
                    self.condition.wait()
                self.active+=1;self.background_active+=int(background);self.requests+=1;self.wait_seconds+=monotonic()-start
            finally:
                self.waiting-=1
                if not background:self.foreground_waiting-=1
        try:yield
        finally:
            with self.condition:self.active-=1;self.background_active-=int(background);self.condition.notify_all()

    def stats(self):
        with self.condition:return {'total':self.total,'background_limit':self.background_limit,'active':self.active,'background_active':self.background_active,'waiting':self.waiting,'foreground_waiting':self.foreground_waiting,'requests':self.requests,'wait_seconds':round(self.wait_seconds,3)}


_gates={'quotes':ResourceGate(),'daily':ResourceGate()}


def configure(config):
    for name,key in [('quotes','market_quote_slots'),('daily','market_daily_slots')]:_gates[name].configure(config.get(key,6),config.get('market_background_slots',4))


def stats():return {name:gate.stats() for name,gate in _gates.items()}


@contextmanager
def resource_slot(kind):
    held=_held.get()
    if kind in held:yield;return
    with _gates[kind].slot(_background.get()):
        token=_held.set(held|{kind})
        try:yield
        finally:_held.reset(token)


def background_task(fn):
    @wraps(fn)
    def run(*args,**kwargs):
        token=_background.set(True)
        try:return fn(*args,**kwargs)
        finally:_background.reset(token)
    return run
