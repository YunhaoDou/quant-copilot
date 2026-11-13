"use client";
import { useState } from "react";
import {useVisiblePoll} from "@/lib/read-resource";
import { marketApiUrl } from "@/lib/live-market";
import { accountStatusText, toAccountView, type TradeView } from "@/lib/account-view";
import { Card, buttonClass } from "./ui";
import PaperAccountCard from "./PaperAccountCard";
import TradeTable, { tradeColumn } from "./TradeTable";
type Result = { quote: { name: string; code: string; price: number }; moving_averages: Record<string, number>; source: { provider: string; quote_time: string; daily_through: string; fetched_at: string }; missing_evidence: string[]; note: string; result: { decision: string; next_action: string; audit_log_id: string; reasons: { msg: string }[] } };
type Forward = { account: { status: string; capital: number; cash: number; equity: number; peak: number; last_checked?: string;
  position: {name: string;symbol: string;quantity: number;stop_loss_price?: number}|null;
  pending: {side:string;symbol:string}|null;
  observations?: {code:string;name:string;time:string;decision:string;missing:string[]}[];
  failures?: string[]; decisions: {time:string;text:string}[];
  trades: {time:string;side:string;symbol:string;price:number;quantity:number}[];
}|null; capture_count: number; capture_dates: string[]; symbols: number; scope: string; limitations: string[] };
export default function TrendLeaderPanel() {
  const [symbol,setSymbol] = useState("600519");
  const [data,setData] = useState<Result|null>(null);
  const [error,setError] = useState("");
  const [busy,setBusy] = useState(false);
  const [forward,setForward] = useState<Forward|null>(null);
  const [actionBusy,setActionBusy] = useState(false);
  async function load(action="", signal?: AbortSignal) {
    try {
      const response = await fetch(`${marketApiUrl()}/trend-forward${action ? "/"+action : ""}`, {method:action ? "POST" : "GET",cache:"no-store",signal});
      const value = await response.json();
      if (!response.ok) throw new Error(value.detail || "账户读取失败");
      setForward(value);
    } catch(e) {if(!signal?.aborted)setError(String(e));}
  }
  useVisiblePoll(signal=>load("",signal),30000);
  async function control(action:string) {setActionBusy(true);await load(action);setActionBusy(false);}
  async function query() {
    setBusy(true); setError(""); setData(null);
    try {
      const response = await fetch(`${marketApiUrl()}/trend-leader/${encodeURIComponent(symbol)}`, {cache:"no-store"});
      const value = await response.json();
      if (!response.ok) throw new Error(value.detail || "核验失败");
      setData(value); await load();
    } catch(e) {setError(String(e));} finally {setBusy(false);}
  }
  const account = forward?.account;
  const accountView = toAccountView(account);
  const trades: TradeView[] | undefined = account?.trades.slice(-20).reverse().map((row) => ({
    time: row.time, symbol: row.symbol, side: row.side, price: row.price, quantity: row.quantity,
  }));
  return <Card><h3 className="text-xl font-semibold">第七策略 · 主线趋势中军波段</h3>
    <p className="mt-2 text-sm leading-7 text-slate-600">主线 → 趋势中军 → 缩量回踩 → 卖点 → 仓位。独立10万元虚拟账户，后台积累真实证据；全部门槛满足后才按后续报价模拟成交。证据不足时保持现金。</p>
    <div className="mt-4 overflow-x-auto"><table className="w-full text-left text-sm leading-7"><thead><tr><th>对比</th><th>主要差别</th></tr></thead><tbody>
      <tr><td className="pr-4">相对强势趋势（最接近）</td><td>原策略偏相对强势与突破；本策略等主线中军缩量回踩和次日确认。</td></tr>
      <tr><td className="pr-4">基本面改善后趋势入场</td><td>原策略以盈利改善为前提；本策略以主线资金持续性为前提。</td></tr>
      <tr><td className="pr-4">情绪龙头回补</td><td>原策略跟踪连板及启动—分歧—回补；本策略做趋势波段，不按固定第几天交易。</td></tr>
    </tbody></table></div>
    <div className="mt-5 border-t pt-4">
      <PaperAccountCard
        bare
        title={`独立前向模拟 · ${accountStatusText(accountView)}`}
        account={accountView}
        busy={actionBusy}
        actions={[
          { id: "start", label: "继续第七策略模拟", onClick: () => control("start") },
          { id: "pause", label: "暂停第七策略模拟", onClick: () => control("pause") },
          { id: "exit", label: "请求第七策略模拟退出", onClick: () => control("exit") },
        ]}
        meta={account && <p className="mt-2 text-xs text-slate-500">最近核验 {account.last_checked || "等待首轮后台采集"}</p>}
        position={account && <p className="mt-3 text-sm">{account.position ? `${account.position.name} ${account.position.symbol} · ${account.position.quantity}股 · 固定止损 ${account.position.stop_loss_price?.toFixed(2) ?? "待核验"}` : "当前空仓；不会为产生交易而放宽规则。"}</p>}
        pending={account?.pending && <p className="mt-2 text-sm">等待后续报价：{account.pending.side === "buy" ? "模拟买入" : "模拟卖出"} {account.pending.symbol}</p>}
      />
      <p className="mt-3 text-sm">真实快照 {forward?.capture_count ?? 0} 份 · 覆盖 {forward?.capture_dates.length ?? 0} 个日期 · 跟踪 {forward?.symbols ?? 0} 只</p>
      <p className="mt-1 text-xs text-slate-500">{forward?.scope}</p>
    </div>
    <form className="mt-4 flex flex-wrap gap-3" onSubmit={e=>{e.preventDefault();query();}}>
      <label className="text-sm">证券代码<input aria-label="趋势中军证券代码" value={symbol} onChange={e=>setSymbol(e.target.value)} pattern="[0-9]{6}" required className="ml-3 rounded-lg border px-3 py-2" /></label>
      <button disabled={busy} className={buttonClass}>{busy ? "正在核验真实数据…" : "读取真实行情并核验"}</button>
    </form>
    {error && <p role="alert" className="mt-3 text-red-700">{error}</p>}
    {data && <div className="mt-4 space-y-3 text-sm leading-7">
      <p className="font-semibold">{data.quote.name}（{data.quote.code}） · 最新报价 {data.quote.price.toFixed(2)}</p>
      <p>{Object.entries(data.moving_averages).map(([n,v])=>`MA${n} ${v.toFixed(2)}`).join(" · ")}</p>
      <p className="text-amber-800">{data.result.decision === "REJECT" ? "证据不足或不符合规则" : "等待核验"} · {data.result.next_action}</p>
      <ul className="list-disc pl-5">{data.missing_evidence.map(x=><li key={x}>待核验：{x}</li>)}</ul>
      <p className="text-xs text-slate-500">{data.source.provider} · 行情 {data.source.quote_time} · 不复权日线截至 {data.source.daily_through}</p>
      <p className="text-xs text-slate-500">{data.note} 审计记录：{data.result.audit_log_id}</p>
    </div>}
    <section className="mt-5 border-t pt-4"><h4 className="font-semibold">本轮核验与等待原因</h4>
      {!forward?.account?.observations?.length && <p className="mt-2 text-sm text-slate-500">等待真实候选和后台核验。可输入证券代码加入跟踪。</p>}
      {forward?.account?.observations?.map(row=><div key={row.code} className="mt-3 text-sm leading-7"><p className="font-medium">{row.name} {row.code} · {row.decision === "BUY_CANDIDATE" ? "候选满足" : row.decision === "EXIT" ? "退出信号" : row.decision === "HOLD" ? "持仓监控" : "等待或不符合"} · {row.time}</p><p className="text-slate-500">{row.missing.join("；")}</p></div>)}
      {forward?.account?.failures?.map(x=><p className="text-sm text-red-700" key={x}>{x}</p>)}
    </section>
    <section className="mt-5 border-t pt-4"><h4 className="font-semibold">模拟成交记录</h4>
      <TradeTable
        rows={trades}
        emptyText="尚无成交。历史统计不代表未来。"
        columns={[tradeColumn("time"), tradeColumn("symbol"), tradeColumn("side"), tradeColumn("price"), tradeColumn("quantity")]}
      />
      <h4 className="mt-4 font-semibold">判断日志</h4>{forward?.account?.decisions.slice(-8).reverse().map((row,i)=><p key={i} className="mt-2 text-xs leading-6 text-slate-500">{row.time} · {row.text}</p>)}
    </section>
    <ul className="mt-5 list-disc pl-5 text-xs leading-6 text-slate-500">{forward?.limitations.map(x=><li key={x}>{x}</li>)}</ul>
  </Card>;
}
