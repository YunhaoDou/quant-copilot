"""vn.py自定义应用桥接引擎，复用唯一模拟账本，不重复执行策略。"""
from datetime import datetime
from queue import Queue, Empty
from threading import Event as StopEvent, Thread
from vnpy.event import Event
from vnpy.trader.engine import BaseEngine
from vnpy.trader.object import AccountData
from .client import LocalClient
from .gateway import GATEWAY_NAME

APP_NAME="QuantCopilot"
EVENT_STATE="eQuantCopilotState"

class QuantCopilotEngine(BaseEngine):
    def __init__(self,main_engine,event_engine):
        super().__init__(main_engine,event_engine,APP_NAME)
        self.client=LocalClient();self.commands=Queue();self.stop=StopEvent();self.snapshot=None;self.account_states={}
        self.thread=Thread(target=self.run,daemon=True,name="QC-seven-strategies");self.thread.start()

    def command(self,strategy=None,action=None):
        self.commands.put((strategy,action))

    def run(self):
        command=(None,None)
        while not self.stop.is_set():
            try:
                if command[0]:self.client.command(*command)
                data=self.client.snapshot();self.snapshot=data
                gateway=self.main_engine.get_gateway(GATEWAY_NAME)
                if gateway:
                    for spec in data["strategies"]:
                        a=spec.get("account")
                        if not a:continue
                        fingerprint=(a["equity"],a["cash"])
                        if self.account_states.get(spec["id"])==fingerprint:continue
                        self.account_states[spec["id"]]=fingerprint
                        gateway.on_account(AccountData(accountid="SIM-"+spec["id"],balance=a["equity"],frozen=max(0,a["equity"]-a["cash"]),gateway_name=GATEWAY_NAME))
                self.event_engine.put(Event(EVENT_STATE,{"connected":True,"data":data,"observed_at":datetime.now().astimezone().isoformat()}))
            except Exception as exc:
                self.event_engine.put(Event(EVENT_STATE,{"connected":False,"error":str(exc)[:250]}))
            try:command=self.commands.get(timeout=15)
            except Empty:command=(None,None)

    def close(self):
        self.stop.set();self.commands.put((None,None));self.thread.join(timeout=1)
