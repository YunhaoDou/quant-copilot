"""启动vn.py 4.5.0及Quant Copilot七策略模拟；不接券商。"""
from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.ui import MainWindow, create_qapp
from vnpy_quant_copilot import QuantCopilotApp, QuantCopilotGateway
from vnpy_quant_copilot.gateway import GATEWAY_NAME
from vnpy_quant_copilot.ui import QuantCopilotManager


def main():
    app=create_qapp()
    events=EventEngine()
    engine=MainEngine(events)
    engine.add_gateway(QuantCopilotGateway)
    engine.add_app(QuantCopilotApp)
    window=MainWindow(engine,events)
    window.showMaximized()
    engine.connect({},GATEWAY_NAME)
    window.open_widget(QuantCopilotManager,"QuantCopilot")
    app.exec()


if __name__=="__main__":main()
