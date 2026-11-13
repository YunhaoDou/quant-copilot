"""vn.py 4.5.0八策略模拟应用。"""
from pathlib import Path
from vnpy.trader.app import BaseApp
from .engine import APP_NAME, QuantCopilotEngine
from .gateway import QuantCopilotGateway

class QuantCopilotApp(BaseApp):
    app_name=APP_NAME
    app_module=__module__
    app_path=Path(__file__).parent
    display_name="A股八策略模拟"
    engine_class=QuantCopilotEngine
    widget_name="QuantCopilotManager"
    icon_name=""
