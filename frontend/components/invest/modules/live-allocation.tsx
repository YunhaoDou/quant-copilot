"use client";
import { useEffect, useState } from "react";
import { marketApiUrl } from "@/lib/live-market";
import { Card, Metric, buttonClass } from "../ui";
import LiveQuotes from "../live-quotes";

export default function LiveAllocation() {
  const [data,setData] = useState<{as_of:string;equity_vs_ma200_pct:number;bond_return_63d_pct:number;note:string} | null>(null), [error,setError] = useState("");
  async function load() { try { const r=await fetch(`${marketApiUrl()}/market/allocation`); const p=await r.json(); if(!r.ok) throw new Error(p.detail);setData(p);setError(""); } catch(e){setError(String(e));} }
  useEffect(()=>{load();},[]);
  return <div className="space-y-4"><LiveQuotes codes={["510300","511010"]}/><Card><h3 className="text-lg font-semibold">A股与国债ETF趋势</h3><button className={`${buttonClass} mt-3`} onClick={load}>更新真实日线</button>{error && <p className="mt-3 text-red-700">{error}</p>}{data && <><p className="my-3 text-xs text-slate-400">历史数据截至{data.as_of}</p><div className="grid gap-3 sm:grid-cols-2"><Metric label="沪深300ETF相对200日均线" value={`${data.equity_vs_ma200_pct.toFixed(2)}%`}/><Metric label="国债ETF近63交易日收益" value={`${data.bond_return_63d_pct.toFixed(2)}%`}/></div><p className="mt-3 text-sm leading-6 text-slate-500">{data.note}</p></>}</Card></div>;
}
