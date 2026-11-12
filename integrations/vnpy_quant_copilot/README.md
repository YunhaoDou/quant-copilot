# vn.py 4.5.0七策略模拟接入

这是原生Qt自定义App与只读公开行情网关，不是CTA策略插件，也不是券商交易接口。
策略计算、真实行情采集和模拟成交继续由Quant Copilot常驻后端承担；vn.py展示并控制同一份七账户账本。
因此关闭vn.py不会停止常驻模拟，也不会产生另一套重复交易。

- 功能 → A股七策略模拟：七个独立页签、继续/暂停/退出、持仓、候选、成交与判断日志。
- QC_PUBLIC_SIM网关：把腾讯公开真实报价快照送到vn.py行情窗口；无逐笔、买卖盘口或券商账户数据。
- 资金窗口中的SIM账户都是虚拟资金；独立持仓在App各页分别展示，避免同代码跨策略相互覆盖。
- 网关send_order始终拒绝，不支持实盘、手工委托或CTA下单。
- 本机接口固定为127.0.0.1:8000；后端停机时显示失联，不以Mock顶替。
- 原观察期2026-11-11、半年复核日、旧成交范围标签和全A股母池保持原样。
- 七策略仍保留原数据与模型限制，接入vn.py不意味着策略已获实盘资格或取得收益保证。

安装位置：将本目录链接到vn.py启动目录，启动器注册QuantCopilotGateway和QuantCopilotApp。
测试使用vn.py自身虚拟环境，无需安装第三方CTA插件。

可复现安装（保留原启动器备份）：

```bash
python3 integrations/install_vnpy_bridge.py --vnpy-dir /Users/douyunhao/Downloads/vnpy-4.5.0
```

回滚时恢复目标目录的 `run_trader.before-quant-copilot.py` 为 `run_trader.py` 即可；不删除任何模拟账户。
