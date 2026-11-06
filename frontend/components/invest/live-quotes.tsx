"use client";

import { useLiveQuotes } from "@/lib/live-market";
import { Card } from "./ui";

export default function LiveQuotes({ codes = ["sh000001", "sz399001", "sz399006"] }: { codes?: string[] }) {
  const { data, error } = useLiveQuotes(codes);
  if (!codes.length) return null;
  return <Card><div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-sm font-semibold">真实行情参考</h3><span className="text-xs text-slate-400">腾讯公开行情 · 30秒刷新 · 以报价时间为准</span></div>{error && <p className="mt-2 text-sm text-red-700">行情不可用：{error}</p>}<div className="mt-3 flex flex-wrap gap-3">{data?.quotes.map(q => <div key={q.symbol} className="min-w-40 flex-1 rounded-xl bg-slate-50 px-4 py-3"><p className="text-xs text-slate-500">{q.name} · {q.code}</p><p className="mt-1 font-semibold tabular-nums">{q.price.toFixed(2)} <span className={q.pct >= 0 ? "text-emerald-700" : "text-red-700"}>{q.pct > 0 ? "+" : ""}{q.pct.toFixed(2)}%</span></p><p className="mt-1 text-[10px] text-slate-400">{new Date(q.quote_time).toLocaleString("zh-CN")}</p></div>)}</div>{!data && !error && <p className="mt-2 text-xs text-slate-400">正在连接…</p>}{data?.missing.length ? <p className="mt-2 text-xs text-amber-700">未返回：{data.missing.join("、")}</p> : null}</Card>;
}
