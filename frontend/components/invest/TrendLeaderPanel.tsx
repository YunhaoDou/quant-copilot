"use client";
import { useState } from "react";
import { marketApiUrl } from "@/lib/live-market";
import { Card, buttonClass } from "./ui";
type Result = { quote: { name: string; code: string; price: number }; moving_averages: Record<string, number>; source: { provider: string; quote_time: string; daily_through: string; fetched_at: string }; missing_evidence: string[]; note: string; result: { decision: string; next_action: string; audit_log_id: string; reasons: { msg: string }[] } };
export default function TrendLeaderPanel() {
  const [symbol,setSymbol] = useState("600519");
  const [data,setData] = useState<Result|null>(null);
  const [error,setError] = useState("");
  const [busy,setBusy] = useState(false);
  async function query() {
    setBusy(true); setError(""); setData(null);
    try {
      const response = await fetch(`${marketApiUrl()}/trend-leader/${encodeURIComponent(symbol)}`, {cache:"no-store"});
      const value = await response.json();
      if (!response.ok) throw new Error(value.detail || "核验失败");
      setData(value);
    } catch(e) {setError(String(e));} finally {setBusy(false);}
  }
  return <Card><h3 className="text-xl font-semibold">趋势中军波段 · 真实数据核验</h3>
    <p className="mt-2 text-sm leading-7 text-slate-600">主线 → 趋势中军 → 缩量回踩 → 卖点 → 仓位。此入口核验公开报价和日线；完整主线及账户证据尚未齐备，暂不参与自动模拟下单。</p>
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
  </Card>;
}
