"use client";
import { useEffect, useState } from "react";
import { marketApiUrl } from "@/lib/live-market";
import { Card, buttonClass, secondaryButtonClass, money } from "./ui";
import TrendLeaderPanel from "./TrendLeaderPanel";
import CycleStrategySimulation from "./CycleStrategySimulation";

type Account = {
  status: string; capital: number; cash: number; equity: number; peak: number; created_at: string;
  position: { symbol: string; name: string; quantity: number; mark: number; mark_time: string } | null;
  pending: { symbol: string; side: string; reason: string } | null;
  candidates?: { code: string; name: string; quote_time: string; status: string; checks: { label: string; passed: boolean | null; value?: number | null; minimum?: number | null; maximum?: number | null }[] }[];
  data?: { generated_at: string; financial_date: string; pool_total: number; checked: number; failures: string[] };
  rules: Record<string, number>;
  decisions: { time: string; text: string }[];
  trades: { time: string; symbol: string; side: string; price: number; quantity: number; pnl: number | null; reason: string }[];
};
type Strategy = { id: string; name: string; logic: string; evidence: string; entry: string; exit: string; source?: string; account: Account | null };
type Payload = { strategies: Strategy[]; refresh: { state: string; error: string | null; updated_at: string | null }; universe: string };
const url = "/invest?view=strategies";
const time = (value: string) => new Date(value).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" });
const status = (value: string) => ({ pass: "条件满足", fail: "条件未满足", unknown: "数据不足" }[value] || value);

export default function StrategyCenterPanel({ strategyId }: { strategyId: string | null }) {
  const [data, setData] = useState<Payload | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState("pass");
  async function load(action = "", signal?: AbortSignal) {
    try {
      const response = await fetch(`${marketApiUrl()}/strategy-center${action}`, { method: action ? "POST" : "GET", cache: "no-store", signal });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "策略读取失败");
      if (payload.strategies) setData(payload);
      else {
        const current = await fetch(`${marketApiUrl()}/strategy-center`, { cache: "no-store", signal });
        if (!current.ok) throw new Error("策略读取失败");
        setData(await current.json());
      }
      setError("");
    } catch (e) { if (!signal?.aborted) setError(String(e)); }
  }
  useEffect(() => {
    const controller = new AbortController();
    load("", controller.signal);
    const timer = setInterval(() => load("", controller.signal), 30000);
    return () => { controller.abort(); clearInterval(timer); };
  }, []);
  async function act(path: string) { setBusy(true); await load(path); setBusy(false); }
  const selected = data?.strategies.find(row => row.id === strategyId);
  const account = selected?.account;
  return <div className="space-y-5">
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-4"><div>
        <h2 className="text-2xl font-semibold">策略研究与独立模拟</h2>
        <p className="mt-2 max-w-3xl text-sm leading-7 text-slate-600">每个策略各用10万元虚拟资金，收益和持仓分别记录。研究方向具有不同程度的历史证据，页面中的具体规则仍需用样本外结果检验。</p>
      </div><div className="flex flex-wrap gap-2">
        <button disabled={busy} className={buttonClass} onClick={() => act("/start-all")}>启动全部独立模拟</button>
        <button disabled={busy} className={secondaryButtonClass} onClick={() => act("/refresh")}>更新候选与日线</button>
      </div></div>
      <p className="mt-3 text-xs leading-6 text-slate-500">{data?.universe} · {data?.refresh.state || "正在读取"}{data?.refresh.error && ` · ${data.refresh.error}`}</p>
      <p className="mt-1 text-xs leading-6 text-slate-500">日线信号使用当前日期以前的已完成交易日，价格和估值来自公开报价。后端在盘中核验并按后续报价撮合，休市时只更新候选观察。T+1、涨跌停等待、整手、费用和滑点沿用影子账户规则，尚未模拟盘口排队与成交量容量。</p>
      <p className="mt-1 text-xs leading-6 text-slate-500">同一轮多个标的满足时，质量价值优先较低PE，红利现金流优先较高历史中位股息率，红利低波优先较低波动，基本面趋势优先较高年报利润增速，相对强势优先较高超额。首版每账户同时持有一只股票。</p>
      {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
    </Card>
    {!selected && <TrendLeaderPanel />}
    {!selected && <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {data?.strategies.map(spec => <Card key={spec.id}>
        <h3 className="text-lg font-semibold">{spec.name}</h3><p className="mt-2 text-sm leading-7 text-slate-600">{spec.logic}</p>
        <p className="mt-3 text-xs leading-6 text-slate-500">{spec.evidence}</p>
        {spec.account && <p className="mt-3 text-sm">{spec.account.status === "running" ? "运行中" : "已暂停"} · 参考权益 {money(spec.account.equity)}</p>}
        <a className={`${secondaryButtonClass} mt-4 inline-flex`} href={`${url}&strategy=${spec.id}`}>打开{spec.name}</a>
      </Card>)}
    </div>}
    {selected && <>
      <nav aria-label="策略页面" className="flex flex-wrap gap-2"><a href={url} className={secondaryButtonClass}>返回策略目录</a>
        {data?.strategies.map(spec => <a className={`${secondaryButtonClass} aria-[current=page]:bg-emerald-50`} aria-current={spec.id === selected.id ? "page" : undefined} href={`${url}&strategy=${spec.id}`} key={spec.id}>{spec.name}</a>)}
      </nav>
      <Card><h3 className="text-xl font-semibold">{selected.name}</h3>
        <dl className="mt-3 space-y-3 text-sm leading-7 text-slate-700">{[["逻辑", selected.logic], ["证据与边界", selected.evidence], ["入场", selected.entry], ["退出", selected.exit]].map(([label,text]) => <div key={label}><dt className="font-semibold">{label}</dt><dd>{text}</dd></div>)}</dl>
        {selected.source && <a href={selected.source} target="_blank" rel="noreferrer" className="mt-3 inline-block text-xs text-emerald-800 underline">原始研究或规则资料</a>}
      </Card>
      {selected.id === "leader-rebound" ? <CycleStrategySimulation /> : <>
        <Card><div className="flex flex-wrap items-center justify-between gap-3">
          <h4 className="font-semibold">独立账户 · {account?.status === "running" ? "运行中" : account ? "已暂停" : "尚未启动"}</h4>
          <div className="flex flex-wrap gap-2">{[["start","继续模拟"],["pause","暂停模拟"],["exit","请求模拟退出"]].map(([action,label]) => <button key={action} disabled={busy} className={secondaryButtonClass} onClick={() => act(`/${selected.id}/${action}`)}>{label}</button>)}</div>
        </div>
        {account && <>
          <div className="mt-4 grid gap-3 sm:grid-cols-4">{[["初始资金",money(account.capital)],["现金",money(account.cash)],["参考权益",money(account.equity)],["回撤",`${((1-account.equity/account.peak)*100).toFixed(2)}%`]].map(([label,value]) => <div key={label}><p className="text-xs text-slate-500">{label}</p><p className="mt-1 text-xl font-semibold">{value}</p></div>)}</div>
          <p className="mt-3 text-xs leading-6 text-slate-500">创建 {time(account.created_at)} · 单仓 {account.rules.position_pct}% · 止损 {account.rules.sim_stop_loss_pct}% · 止盈 {account.rules.sim_take_profit_pct}%</p>
          <p className="mt-2 text-sm">{account.position ? `${account.position.name} ${account.position.symbol} · ${account.position.quantity}股 · 最近估值价${account.position.mark.toFixed(3)} · ${time(account.position.mark_time)}` : "当前无模拟持仓"}</p>
          {account.pending && <p className="mt-2 text-sm text-amber-800">待处理 {account.pending.symbol} · {account.pending.side === "buy" ? "模拟买单" : "模拟卖单"} · {account.pending.reason}</p>}
        </>}
        </Card>
        <Card><h4 className="font-semibold">逐项候选核验</h4>
          {account?.data && <p className="mt-2 text-xs leading-6 text-slate-500">财务快照 {account.data.financial_date} · 本轮日线核验 {account.data.checked}/{account.data.pool_total} 只 · 生成 {time(account.data.generated_at)} · 失败 {account.data.failures.length} 项</p>}
          <label className="mt-3 block text-sm">显示候选<select className="ml-2 rounded-lg border p-2" value={filter} onChange={e => setFilter(e.target.value)}><option value="pass">条件满足</option><option value="all">全部</option><option value="unknown">数据不足</option></select></label>
          <div className="mt-3 space-y-3">{account?.candidates?.filter(row => filter === "all" || row.status === filter).map(row => <details className="border-t pt-3 text-sm" key={row.code}>
            <summary className="cursor-pointer font-medium">{row.name} {row.code} · {status(row.status)}</summary>
            <p className="mt-2 text-xs text-slate-500">报价 {time(row.quote_time)}</p>
            <ul className="mt-2 space-y-1 text-xs leading-6">{row.checks.map(item => <li key={item.label} className={item.passed ? "text-emerald-800" : "text-slate-600"}>{item.label} · {item.value == null ? "" : Number(item.value.toFixed(2))} · {item.passed === null ? "未知" : item.passed ? "满足" : "未满足"}{item.minimum != null && ` · 下限 ${item.minimum}`}{item.maximum != null && ` · 上限 ${item.maximum}`}</li>)}</ul>
          </details>)}</div>
          {!account?.candidates?.some(row => filter === "all" || row.status === filter) && <p className="mt-3 text-sm text-slate-500">当前没有此类候选。可切换全部查看，或等待数据核验。</p>}
        </Card>
        <Card><h4 className="font-semibold">判断日志</h4><div className="mt-3 max-h-80 overflow-auto">{account?.decisions.slice().reverse().map((row,i) => <div key={i} className="border-t py-3 text-sm leading-7"><p className="text-xs text-slate-500">{time(row.time)}</p><p>{row.text}</p></div>)}</div></Card>
        <Card><h4 className="font-semibold">模拟成交流水</h4><div className="mt-3 overflow-x-auto"><table className="w-full min-w-[620px] text-left text-xs"><thead><tr>{["时间","股票","方向","模拟价格","股数","净盈亏","原因"].map(text => <th className="py-2" key={text}>{text}</th>)}</tr></thead><tbody>{account?.trades.map((row,i) => <tr key={i} className="border-t"><td className="py-2">{time(row.time)}</td><td>{row.symbol}</td><td>{row.side === "buy" ? "买入" : "卖出"}</td><td>{row.price.toFixed(3)}</td><td>{row.quantity}</td><td>{row.pnl === null ? "—" : money(row.pnl)}</td><td>{row.reason}</td></tr>)}</tbody></table></div>
          {!account?.trades.length && <p className="mt-3 text-sm text-slate-500">尚无模拟成交，等待有效信号和后续可成交报价。</p>}
        </Card>
      </>}
    </>}
  </div>;
}
