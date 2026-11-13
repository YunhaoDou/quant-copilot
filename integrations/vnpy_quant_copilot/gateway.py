"""只读公开行情快照网关；禁止所有交易委托，不接入券商。"""
from datetime import datetime
import re
from threading import Event, Lock, Thread
from vnpy.trader.gateway import BaseGateway
from vnpy.trader.constant import Exchange, Product
from vnpy.trader.object import TickData, ContractData
from .client import LocalClient

GATEWAY_NAME="QC_PUBLIC_SIM"

def exchange_for(code):
    return Exchange.BSE if code.startswith(("4","8","92")) else Exchange.SSE if code.startswith(("5","6","9")) else Exchange.SZSE

class QuantCopilotGateway(BaseGateway):
    default_name=GATEWAY_NAME
    default_setting={"说明":"真实公开报价快照；模拟账户；不接受委托"}
    exchanges=[Exchange.SSE,Exchange.SZSE,Exchange.BSE]

    def __init__(self,event_engine,gateway_name):
        super().__init__(event_engine,gateway_name)
        self.client=LocalClient();self.stop=Event();self.lock=Lock();self.thread=None
        self.symbols={"510300","600519","000001","000333","600900","601318","600036","300750","002594"}
        self.last_times={};self.contracts=set()

    def connect(self,setting):
        if self.thread and self.thread.is_alive():return
        self.stop.clear();self.thread=Thread(target=self.run,daemon=True,name="QC-public-quotes");self.thread.start()
        self.write_log("启动真实公开行情快照。无逐笔/盘口；不接受实盘或手工委托。")

    def publish(self,q):
        code=q["code"];stamp=q.get("quote_time")
        if not stamp or not q.get("price") or q["price"]<=0:return
        if self.last_times.get(code)==stamp:return
        exchange=exchange_for(code)
        if code not in self.contracts:
            self.on_contract(ContractData(symbol=code,exchange=exchange,name=q["name"],product=Product.ETF if code.startswith(("5","15","16")) else Product.EQUITY,size=1,pricetick=.001 if code.startswith(("5","15","16")) else .01,min_volume=200 if code.startswith("688") else 100,gateway_name=self.gateway_name))
            self.contracts.add(code)
        self.on_tick(TickData(symbol=code,exchange=exchange,datetime=datetime.fromisoformat(stamp),
            name=q["name"],last_price=q["price"],pre_close=q.get("previous_close") or 0,
            open_price=q.get("open") or 0,high_price=q.get("high") or 0,low_price=q.get("low") or 0,
            volume=(q.get("volume_lots") or 0)*100,turnover=q.get("amount_yuan") or 0,gateway_name=self.gateway_name))
        self.last_times[code]=stamp

    def run(self):
        previous_error=None
        while not self.stop.is_set():
            try:
                with self.lock:codes=sorted(self.symbols)
                for start in range(0,len(codes),100):
                    data=self.client.quotes(codes[start:start+100])
                    for q in data["quotes"]:self.publish(q)
                    if data.get("missing"):self.write_log("部分订阅报价缺失："+",".join(data["missing"]))
                if previous_error:self.write_log("公开报价连接已恢复")
                previous_error=None
            except Exception as exc:
                message=str(exc)
                if message!=previous_error:self.write_log("公开报价不可用，保留最后快照："+message[:180])
                previous_error=message
            self.stop.wait(15)

    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(timeout=1)

    def subscribe(self,req):
        if not re.fullmatch(r"\d{6}",req.symbol) or req.exchange!=exchange_for(req.symbol):
            self.write_log("订阅失败：请输入正确交易所的六位A股或场内基金代码");return
        with self.lock:self.symbols.add(req.symbol)

    def send_order(self,req):
        self.write_log("委托已拒绝：本接口只读；请在八策略App操作模拟账户。")
        return ""

    def cancel_order(self,req):self.write_log("撤单已拒绝：本接口没有交易委托。")
    def query_account(self):self.write_log("八个虚拟账户由八策略App同步；没有券商资金账户。")
    def query_position(self):self.write_log("请在八策略App分别查看虚拟持仓，不合并为券商持仓。")
