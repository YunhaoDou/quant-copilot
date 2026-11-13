"""八个独立模拟策略的原生Qt界面。"""
from html import escape
import math
from vnpy.trader.ui import QtCore, QtWidgets
from .client import STRATEGIES
from .engine import APP_NAME, EVENT_STATE


def text(value):return escape(str(value if value is not None else "—"))
def money(value):
    try:return f"{float(value):,.2f}" if math.isfinite(float(value)) else "—"
    except (TypeError,ValueError):return "—"


def report(spec):
    a=spec.get("account") or {}
    if not a:return "<p>尚未启动模拟账户。</p>"
    position=a.get("position");pending=a.get("pending")
    equity=a.get("equity",0);capital=a.get("capital",0);peak=a.get("peak",0)
    gain=(equity/capital-1)*100 if capital else 0;drawdown=(1-equity/peak)*100 if peak else 0
    stats=[("初始虚拟资金",money(capital)),("可用现金",money(a.get("cash"))),("参考权益",money(equity)),("参考收益",f"{gain:.2f}%"),("距历史高点回撤",f"{drawdown:.2f}%")]
    body='<table width="100%"><tr>'+''.join(f'<th>{text(k)}</th>' for k,v in stats)+'</tr><tr>'+''.join(f'<td>{text(v)}</td>' for k,v in stats)+'</tr></table>'
    body+='<h3>策略与边界</h3><p>'+text(spec.get("logic"))+'</p><p>入场：'+text(spec.get("entry"))+'</p><p>退出：'+text(spec.get("exit"))+'</p>'
    body+='<h3>独立模拟持仓</h3>'
    for p in a.get("positions",{}).values():body+='<p>'+text(p.get("name"))+' '+text(p.get("symbol"))+' · '+text(p.get("quantity"))+'份 · 参考价 '+money(p.get("mark"))+'</p>'
    body+=('<p>'+text(position.get("name"))+' '+text(position.get("symbol"))+' · '+text(position.get("quantity"))+'股 · 参考价 '+money(position.get("mark"))+' · 固定止损 '+money(position.get("stop_loss_price"))+'</p>') if position else ('<p>当前空仓。条件不满足或证据不足时不建仓。</p>' if not a.get('positions') else '')
    if pending:body+='<p>待处理模拟计划：'+text(pending.get("symbol"))+' · '+text(pending.get("reason"))+'</p>'
    data=a.get("data") or {}
    if data:body+='<p>全母池 '+text(data.get("pool_total"))+'只 · 日线核验尝试 '+text(data.get("checked"))+'只 · 不足/失败 '+text(len(data.get("failures",[])))+'只 · 更新 '+text(data.get("generated_at"))+'</p>'
    body+='<h3>本轮候选 / 等待原因</h3>'
    rows=a.get("observations") or a.get("candidates") or []
    if not rows:body+='<p>等待后台核验。运行中不代表已经满足交易条件。</p>'
    for row in rows[:20]:
        status={"pass":"满足候选条件","unknown":"证据不足","fail":"不符合","REJECT":"拒绝 / 缺证据","WAIT":"等待","HOLD":"持仓核对","EXIT":"退出信号","BUY_CANDIDATE":"候选满足"}.get(row.get("status") or row.get("decision"),"待核验")
        detail='；'.join(row.get("missing") or [c["label"] for c in row.get("checks",[]) if c.get("passed") is not True])
        body+='<p><b>'+text(row.get("name"))+' '+text(row.get("code"))+' · '+text(status)+'</b><br>'+text(detail)+'</p>'
    body+='<h3>模拟成交流水</h3><table width="100%"><tr><th>供应商报价时间</th><th>证券</th><th>方向</th><th>模拟价格</th><th>股数</th><th>范围</th></tr>'
    trades=a.get("trades",[])
    for row in trades[-30:][::-1]:body+='<tr>'+''.join('<td>'+text(v)+'</td>' for v in (row.get("time"),row.get("symbol"),"买入" if row.get("side")=="buy" else "卖出",money(row.get("price")),row.get("quantity"),row.get("universe_scope") or "原始记录"))+'</tr>'
    if not trades:body+='<tr><td colspan="6">尚无模拟成交；不回填过去价格。</td></tr>'
    body+='</table><h3>判断日志</h3>'
    for row in a.get("decisions",[])[-10:][::-1]:body+='<p>'+text(row.get("time"))+' · '+text(row.get("text"))+'</p>'
    for error in a.get("failures",[])[:5]:body+='<p>取数失败：'+text(error)+'</p>'
    return '<html><head><style>body{color:#dce8e4;font-size:13px;font-family: sans-serif;}h3{color:#83d3b1;margin-top:22px;}table{border-collapse:collapse;}th,td{padding:8px;border-bottom:1px solid #3e514c;text-align:left;}th{color:#9bb7ae;}p{line-height:1.7;}</style></head><body>'+body+'</body></html>'

class QuantCopilotManager(QtWidgets.QWidget):
    signal_state=QtCore.Signal(object)

    def __init__(self,main_engine,event_engine):
        super().__init__();self.main_engine=main_engine;self.event_engine=event_engine
        self.engine=main_engine.get_engine(APP_NAME)
        self.setWindowTitle("A股八策略模拟 · Quant Copilot × vn.py 4.5.0");self.resize(1200,850)
        self.setStyleSheet("QWidget{background:#152720;color:#dfebe5;}QPushButton{padding:8px 15px;background:#244e3c;border:1px solid #44725b;border-radius:5px;}QPushButton:disabled{color:#65796e;}QTabBar::tab{padding:10px;}QTextBrowser{border:0;background:#192e25;}")
        root=QtWidgets.QVBoxLayout(self)
        title=QtWidgets.QLabel("A股八策略模拟");title.setStyleSheet("font-size:25px;font-weight:bold;color:#8bd4b1;padding:8px;");root.addWidget(title)
        note=QtWidgets.QLabel("全部为虚拟账户；真实公开报价为定时快照，非逐笔行情。策略由Quant Copilot常驻服务执行，本窗口不另开交易账本。")
        note.setWordWrap(True);root.addWidget(note)
        self.status_label=QtWidgets.QLabel("正在连接本机模拟服务…");self.status_label.setWordWrap(True);root.addWidget(self.status_label)
        self.refresh=QtWidgets.QPushButton("刷新八策略状态");self.refresh.clicked.connect(lambda:self.engine.command());root.addWidget(self.refresh)
        self.tabs=QtWidgets.QTabWidget();root.addWidget(self.tabs)
        self.pages={};self.buttons=[];self.latest_payload=None;self.rendered_html={}
        self.tabs.currentChanged.connect(self.render_selected)
        for identifier,name in STRATEGIES.items():
            page=QtWidgets.QWidget();layout=QtWidgets.QVBoxLayout(page);controls=QtWidgets.QHBoxLayout()
            label=QtWidgets.QLabel("等待账户状态");controls.addWidget(label);controls.addStretch()
            for action,caption in (("start","继续模拟"),("pause","暂停模拟"),("exit","请求模拟退出")):
                button=QtWidgets.QPushButton(caption);button.setEnabled(False)
                button.clicked.connect(lambda checked=False,s=identifier,a=action:self.control(s,a));controls.addWidget(button);self.buttons.append(button)
            layout.addLayout(controls);browser=QtWidgets.QTextBrowser();browser.setOpenLinks(False);browser.setOpenExternalLinks(False);layout.addWidget(browser)
            self.tabs.addTab(page,name);self.pages[identifier]=(label,browser)
        self.signal_state.connect(self.render);event_engine.register(EVENT_STATE,self.process_event)
        if self.engine.snapshot:self.render({"connected":True,"data":self.engine.snapshot,"observed_at":"已保存快照"})

    def process_event(self,event):
        self.signal_state.emit(event.data)

    def control(self,strategy,action):
        for button in self.buttons:button.setEnabled(False)
        self.status_label.setText("正在提交模拟控制，等待后台返回…")
        self.engine.command(strategy,action)

    def showEvent(self,event):
        super().showEvent(event)
        if self.latest_payload:self.render(self.latest_payload)

    def render_selected(self,*args):
        if not self.latest_payload or not self.latest_payload.get("connected") or not self.isVisible():return
        identifier=list(STRATEGIES)[self.tabs.currentIndex()]
        spec=next(s for s in self.latest_payload["data"]["strategies"] if s["id"]==identifier)
        html=report(spec)
        if self.rendered_html.get(identifier)==html:return
        browser=self.pages[identifier][1];scroll=browser.verticalScrollBar().value()
        browser.setHtml(html);browser.verticalScrollBar().setValue(scroll)
        self.rendered_html[identifier]=html

    def render(self,payload):
        self.latest_payload=payload
        if not self.isVisible():return
        connected=payload.get("connected")
        for button in self.buttons:button.setEnabled(bool(connected))
        if not connected:
            self.status_label.setText("本机模拟服务不可用，当前显示上次快照："+str(payload.get("error","")));return
        data=payload["data"];experiment=data.get("experiment") or {};scan=data.get("market_scan") or {};progress=data.get("refresh") or {}
        self.status_label.setText(f"已连接 · 共同观察期 {experiment.get('start_date','待确认')} 至 {experiment.get('review_date','待确认')}复核 · 官方母池 {scan.get('total',0)}只 · 日线核验 {progress.get('checked',0)}/{progress.get('total',0)} · 本地同步 {payload.get('observed_at','')}")
        for spec in data["strategies"]:
            label,browser=self.pages[spec["id"]];account=spec.get("account") or {}
            label.setText("运行中" if account.get("status")=="running" else "已暂停" if account else "尚未启动")
        self.render_selected()
