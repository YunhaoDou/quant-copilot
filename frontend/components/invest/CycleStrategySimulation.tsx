"use client";
import { useEffect, useState } from "react";
import { marketApiUrl } from "@/lib/live-market";
import { Card, buttonClass, secondaryButtonClass, money } from "./ui";

type Account = {
  status: string; created_at: string; capital: number; cash: number; equity: number; peak: number;
  position: { name: string; symbol: string; quantity: number; entry_price: number; mark: number; mark_time: string } | null;
  pending: { side: string; symbol: string; reason: string; signal_time: string } | null;
  rules: Record<string, number>;
  decisions: { time: string; text: string; event_id: string | null }[];
  trades: { time: string; side: string; symbol: string; quantity: number; price: number; pnl: number | null; reason: string }[];
};
const stamp = (value: string) => new Date(value).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" });

export default function CycleStrategySimulation() {
  const [account, setAccount] = useState<Account | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function load(action = "", signal?: AbortSignal) {
    try {
      const response = await fetch(`${marketApiUrl()}/cycle/strategy-sim${action}`, { method: action ? "POST" : "GET", cache: "no-store", signal });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "读取模拟账户失败");
      setAccount(data.account); setError("");
    } catch (e) { if (!signal?.aborted) setError(String(e)); }
  }
  useEffect(() => {
    const controller = new AbortController();
    load("", controller.signal);
    const timer = setInterval(() => load("", controller.signal), 30000);
    return () => { controller.abort(); clearInterval(timer); };
  }, []);
  async function control(action: string) {
    setBusy(true); await load(action); setBusy(false);
  }
  return <div className="space-y-5">
    <Card><div className="flex flex-wrap justify-between gap-3">
      <div><h3 className="text-xl font-semibold">启动—分歧—回补 · 策略模拟</h3><p className="mt-2 text-sm leading-7 text-slate-600">后台根据事件证据管理独立虚拟账户，记录等待、信号及后续报价撮合。账户、持仓和流水保存在本地后端。</p></div>
      <div className="flex flex-wrap gap-2">
        <button disabled={busy || account?.status === "running"} className={buttonClass} onClick={() => control("/start")}>{account ? "继续模拟" : "启动模拟"}</button>
        <button disabled={busy || account?.status !== "running"} className={secondaryButtonClass} onClick={() => control("/pause")}>暂停模拟</button>
        <button disabled={busy || (!account?.position && !account?.pending)} className={secondaryButtonClass} onClick={() => control("/exit")}>请求模拟退出</button>
        <button className={secondaryButtonClass} onClick={() => load()}>刷新模拟账户</button>
      </div>
    </div>{error && <p role="alert" className="mt-3 text-red-700">{error}</p>}</Card>
    <Card><h4 className="font-semibold">本轮规则与假设</h4><ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-7 text-slate-700">
      <li>首次事件必须有大盘新低证据，且事件人工阶段已确认启动或回补。缺少这些依据时持续等待，并写明原因。</li>
      <li>启动后第1至2个已采集交易日期观察板块候选首位；第3个采集日期采取减险退出；第4个采集日期仅在人工确认回补后再观察进入，第5个采集日期退出。这是待检验的时间假设，采集缺口会影响日期计数。</li>
      <li>模拟信号最早使用下一可得报价撮合。采用T+1，涨停买单及跌停卖单等待，风险警示或价格字段不足时不成交。公开报价无法还原盘口排队与真实成交量，结果需结合成交记录评价。</li>
      <li>默认本金10万元、单仓10%、价格止损8%、止盈15%、组合回撤防线20%。费用与滑点读取项目配置。首版同时持有一只股票，每事件每阶段最多进入一次。</li>
      <li>冰点逆势连板、电风扇轮动及盘中洗盘意图仍需证据化定义。当前自动模拟聚焦启动、人工确认的回补及风险退出。</li>
    </ul></Card>
    {account && <>
      <Card><h4 className="font-semibold">模拟账户 · {account.status === "running" ? "运行中" : "已暂停"}</h4>
        <div className="mt-4 grid gap-4 sm:grid-cols-4">{[
          ["起始资金", money(account.capital)], ["现金", money(account.cash)],
          ["参考权益", money(account.equity)], ["峰值回撤", `${((1-account.equity/account.peak)*100).toFixed(2)}%`],
        ].map(([label, value]) => <div key={label}><p className="text-xs text-slate-500">{label}</p><p className="mt-1 text-xl font-semibold">{value}</p></div>)}</div>
        <p className="mt-3 text-xs text-slate-500">启动 {stamp(account.created_at)} · 单仓 {account.rules.position_pct}% · 止损 {account.rules.sim_stop_loss_pct}% · 止盈 {account.rules.sim_take_profit_pct}%</p>
        <p className="mt-3 text-sm">{account.position ? `${account.position.name} ${account.position.symbol} · ${account.position.quantity}股 · 入场 ${account.position.entry_price.toFixed(3)} · 参考价 ${account.position.mark.toFixed(3)} · ${stamp(account.position.mark_time)}` : "当前无模拟持仓"}</p>
        {account.pending && <p className="mt-2 text-sm text-amber-800">待处理模拟{account.pending.side === "buy" ? "买单" : "卖单"} · {account.pending.symbol} · {account.pending.reason}</p>}
      </Card>
      <Card><h4 className="font-semibold">策略判断日志</h4><div className="mt-3 max-h-96 overflow-auto">
        {account.decisions.slice().reverse().map((decision, i) => <div className="border-t py-3 text-sm leading-7" key={i}><p className="text-xs text-slate-500">{stamp(decision.time)}</p><p>{decision.text}</p></div>)}
        {!account.decisions.length && <p className="text-sm text-slate-500">等待后台收到启动后的新鲜事件报价。</p>}
      </div></Card>
      <Card><h4 className="font-semibold">模拟成交流水</h4><div className="mt-3 overflow-x-auto"><table className="w-full min-w-[620px] text-left text-xs"><thead><tr>{["时间", "股票", "方向", "数量", "模拟价", "已实现盈亏", "原因"].map(label => <th className="py-2" key={label}>{label}</th>)}</tr></thead><tbody>
        {account.trades.map((trade, i) => <tr className="border-t" key={i}><td className="py-3">{stamp(trade.time)}</td><td>{trade.symbol}</td><td>{trade.side === "buy" ? "买入" : "卖出"}</td><td>{trade.quantity}</td><td>{trade.price.toFixed(3)}</td><td>{trade.pnl === null ? "—" : money(trade.pnl)}</td><td>{trade.reason}</td></tr>)}
      </tbody></table></div>{!account.trades.length && <p className="mt-3 text-sm text-slate-500">尚无模拟成交，请先查看判断日志中的等待条件。</p>}</Card>
    </>}
  </div>;
}
