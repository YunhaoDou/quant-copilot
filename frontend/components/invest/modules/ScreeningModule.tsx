"use client";

import { useEffect, useState } from "react";

import { getApiUrl, type ScreeningResponse } from "@/lib/api";
import {useReadResource,useDebouncedValue} from "@/lib/read-resource";
import { useLocale } from "@/lib/i18n";

const pct = (n: number | null | undefined) => (n == null || !Number.isFinite(n) ? "—" : `${(n * 100).toFixed(1)}%`);
const num = (n: number | null | undefined, digits = 2) => (n == null || !Number.isFinite(n) ? "—" : n.toFixed(digits));

export default function ScreeningModule() {
  const { locale, t } = useLocale();
  const [page,setPage]=useState(1),[query,setQuery]=useState(""),[actionError,setActionError]=useState("");
  const debounced=useDebouncedValue(query);
  type Snapshot=ScreeningResponse&{snapshot_version:string;matched:number};
  const summary=useReadResource<Snapshot>(`${getApiUrl()}/screening/summary`,d=>d?.status==="running"?2000:15000);
  const params=new URLSearchParams({page:String(page),query:debounced,...(summary.data?.snapshot_version?{version:summary.data.snapshot_version}:{})});
  const result=useReadResource<Snapshot>(`${getApiUrl()}/screening/results?${params}`,0);
  useEffect(()=>{if(result.errorStatus===409)summary.refresh();},[result.errorStatus,summary.refresh]);
  const data=result.data,rows=data?.results||[];
  const status=actionError||result.error||summary.error||summary.data?.progress||`全A股 ${summary.data?.universe_size??0} 只 · 已评分 ${summary.data?.scored??0} · 数据不足 ${summary.data?.unknown??0}`;
  async function run(){setActionError("");try{const r=await fetch(`${getApiUrl()}/screening/refresh`,{method:"POST"});if(!r.ok)throw new Error("扫描请求失败");summary.refresh();}catch(e){setActionError(String(e));}}

  return (
    <main className="max-w-4xl mx-auto p-10">
      <h1 className="text-2xl font-medium">{t("screening.title")}</h1>
      <p className="text-sm text-gray-500 mt-1">{t("screening.desc")}</p>

      <button className="mt-6 border rounded px-3 py-1.5 bg-black text-white text-sm" onClick={run}>
        {t("screening.run")}
      </button>
      {result.loading&&<p role="status" className="mt-3 text-xs text-slate-500">正在查询完整母池…</p>}
      {status && <p className="mt-3 text-sm text-gray-600">{status}</p>}

      <label className="mt-4 block text-sm">查询完整A股结果<input aria-label="查询完整A股结果" className="ml-3 rounded border p-2" value={query} onChange={e=>{setQuery(e.target.value);setPage(1);}} placeholder="代码或名称"/></label>
      {data && data.results.length > 0 && (
        <div className="mt-6 overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="text-left text-gray-400 border-b">
                <th className="py-2 pr-3">#</th>
                <th className="py-2 pr-3">{t("screening.symbol")}</th>
                <th className="py-2 pr-3">{t("screening.score")}</th>
                <th className="py-2 pr-3">{t("screening.mom3m")}</th>
                <th className="py-2 pr-3">{t("screening.mom12m")}</th>
                <th className="py-2 pr-3">{t("screening.fundFlow")}</th>
                <th className="py-2 pr-3">{t("screening.why")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.symbol} className="border-b last:border-0">
                  <td className="py-2 pr-3 text-gray-400">{r.rank??"—"}</td>
                  <td className="py-2 pr-3 font-medium">{r.symbol}</td>
                  <td className="py-2 pr-3">{num(r.composite_score)}</td>
                  <td className="py-2 pr-3">{pct(r.factors.momentum_3m)}</td>
                  <td className="py-2 pr-3">{pct(r.factors.momentum_12m)}</td>
                  <td className="py-2 pr-3">{num(r.factors.fund_flow_score, 1)}</td>
                  <td className="py-2 pr-3 text-gray-500">{r.reasons.join(", ") || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data && data.results.length > 0 && <div className="mt-4 flex items-center gap-3 text-sm"><button disabled={page<=1} onClick={()=>setPage(p=>p-1)}>上一页</button><span>第{page}/{Math.max(1,Math.ceil((data.matched??0)/50))}页 · 全部{data.universe_size}只，每页50只；包含数据不足证券</span><button disabled={page>=Math.max(1,Math.ceil((data.matched??0)/50))} onClick={()=>setPage(p=>p+1)}>下一页</button></div>}
      {data && data.results.length === 0 && (
        <p className="mt-6 text-sm text-gray-500">{t("screening.empty")}</p>
      )}
    </main>
  );
}
