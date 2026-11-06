"use client";
import { useState } from "react";
import { marketApiUrl } from "@/lib/live-market";
import { Card, Field, Metric, inputClass, buttonClass } from "../ui";
import LiveQuotes from "../live-quotes";
type Result = { label:string;strategy_key:string;total_return:number;max_drawdown:number;num_trades:number };
export default function LiveStrategyLab() {
  const [code,setCode]=useState("510300"),[data,setData]=useState<{as_of:string;results:Result[];note:string}|null>(null),[status,setStatus]=useState("");
  async function run(){setStatus("正在读取真实日线并计算…");setData(null);try{const r=await fetch(`${marketApiUrl()}/market/strategy-lab?symbol=${encodeURIComponent(code)}`);const p=await r.json();if(!r.ok)throw new Error(p.detail);setData(p);setStatus("");}catch(e){setStatus(String(e));}}
  return <div className="space-y-4"><LiveQuotes codes={[code]}/><Card><h3 className="text-lg font-semibold">A股策略实验室</h3><div className="mt-4 flex items-end gap-3"><Field label="股票或场内ETF代码"><input className={inputClass} value={code} onChange={e=>setCode(e.target.value)}/></Field><button className={buttonClass} onClick={run}>运行历史实验</button></div>{status && <p className="mt-3 text-sm text-slate-500">{status}</p>}{data && <><p className="mt-4 text-xs text-amber-800">{data.note} 数据截至{data.as_of}。</p><div className="mt-4 grid gap-3 sm:grid-cols-2">{data.results.map(r=><div key={r.strategy_key} className="space-y-2"><Metric label={r.label} value={`${(r.total_return*100).toFixed(2)}%`} hint={`模型最大回撤${(r.max_drawdown*100).toFixed(2)}% · ${r.num_trades}笔模拟成交`}/></div>)}</div></>}</Card></div>;
}
