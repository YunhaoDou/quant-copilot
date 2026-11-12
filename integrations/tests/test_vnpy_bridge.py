"""vn.py桥接单元测试；合成输入不写入真实模拟账户。"""
import copy
import unittest
from vnpy.event import EventEngine, Event
from vnpy.trader.ui import QtWidgets
from vnpy_quant_copilot.client import LocalClient, STRATEGIES
from vnpy_quant_copilot.gateway import QuantCopilotGateway, exchange_for
from vnpy_quant_copilot.ui import QuantCopilotManager, report
from vnpy.trader.constant import Exchange


def snapshot():
    return {"strategies":[{"id":identifier,"name":name,"logic":"测试规则","entry":"测试证据","exit":"测试退出","account":{"status":"running","capital":100000,"cash":100000,"equity":100000,"peak":100000,"position":None,"pending":None,"trades":[],"decisions":[]}} for identifier,name in STRATEGIES.items()],"experiment":{"start_date":"2026-11-11","review_date":"2027-05-11"},"market_scan":{"total":5580},"refresh":{"checked":5580,"total":5580}}

class FakeClient(LocalClient):
    def __init__(self):self.calls=[]
    def request(self,path,method="GET"):
        self.calls.append((path,method))
        return snapshot() if path=="/strategy-center" else {"account":{"status":"paused","capital":100000}}

class ClientTests(unittest.TestCase):
    def test_rejects_remote_and_credential_urls(self):
        for url in ("https://127.0.0.1:8000","http://example.com","http://user@127.0.0.1:8000","http://127.0.0.1:8000/a"):
            with self.assertRaises(ValueError):LocalClient(url)

    def test_routes_all_seven_controls_only_to_paper_endpoints(self):
        c=FakeClient()
        for identifier in STRATEGIES:
            for action in ("start","pause","exit"):c.command(identifier,action)
        self.assertEqual(len(c.calls),21)
        self.assertIn(("/trend-forward/exit","POST"),c.calls)
        self.assertIn(("/cycle/strategy-sim/pause","POST"),c.calls)
        with self.assertRaises(ValueError):c.command("unknown","start")
        with self.assertRaises(ValueError):c.command("quality-value","buy")

    def test_legacy_account_is_merged_without_resetting_others(self):
        c=FakeClient();data=c.snapshot()
        self.assertEqual(len(data['strategies']),7)
        self.assertEqual(next(s for s in data['strategies'] if s['id']=='leader-rebound')['account']['status'],'paused')
        self.assertEqual(data['strategies'][0]['account']['equity'],100000)

class GatewayTests(unittest.TestCase):
    def test_snapshot_ticks_are_deduplicated_and_never_fabricate_orderbook(self):
        g=QuantCopilotGateway(EventEngine(),"TEST");ticks=[];contracts=[]
        g.on_tick=ticks.append;g.on_contract=contracts.append
        q={'code':'920001','name':'合成样本','price':10,'quote_time':'2026-11-12T15:00:00+08:00','volume_lots':2}
        g.publish(q);g.publish(q)
        self.assertEqual(len(ticks),1);self.assertEqual(len(contracts),1)
        self.assertEqual(ticks[0].exchange,Exchange.BSE);self.assertEqual(ticks[0].volume,200)
        self.assertEqual(ticks[0].bid_price_1,0)
        self.assertEqual(exchange_for('600519'),Exchange.SSE)

    def test_gateway_rejects_orders(self):
        g=QuantCopilotGateway(EventEngine(),"TEST");logs=[];g.write_log=logs.append
        self.assertEqual(g.send_order(None),"");self.assertIn('委托已拒绝',logs[0])
        g.cancel_order(None);self.assertIn('撤单已拒绝',logs[-1])

class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    def test_seven_native_pages_controls_and_offline_status(self):
        class Bridge:
            snapshot=None
            def __init__(self):self.calls=[]
            def command(self,*args):self.calls.append(args)
        bridge=Bridge()
        class Main:
            def get_engine(self,*a):return bridge
        w=QuantCopilotManager(Main(),EventEngine());w.show();self.app.processEvents();w.process_event(Event('eQuantCopilotState',{'connected':True,'data':snapshot()}))
        self.assertEqual(w.tabs.count(),7);self.assertEqual(len(w.buttons),21)
        self.assertIn('5580',w.status_label.text())
        w.buttons[0].click();self.assertEqual(bridge.calls[-1],('quality-value','start'))
        w.render({'connected':False,'error':'服务停止'})
        self.assertIn('上次快照',w.status_label.text());self.assertFalse(w.buttons[0].isEnabled())
        w.close()
        previous=w.pages['quality-value'][1].toHtml()
        changed=snapshot();changed['strategies'][0]['account']['cash']=50000
        w.process_event(Event('eQuantCopilotState',{'connected':True,'data':changed}))
        self.assertEqual(w.pages['quality-value'][1].toHtml(),previous)
        w.show();self.app.processEvents()
        self.assertIn('50,000.00',w.pages['quality-value'][1].toPlainText())
        w.close()
    def test_untrusted_text_is_escaped(self):
        spec=snapshot()['strategies'][0];spec['logic']='<script>alert(1)</script>'
        self.assertNotIn('<script>',report(spec));self.assertIn('&lt;script&gt;',report(spec))

if __name__=='__main__':unittest.main()
