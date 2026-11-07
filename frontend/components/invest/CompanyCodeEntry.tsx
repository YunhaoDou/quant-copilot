"use client";
import { useEffect, useState } from "react";
import { companyCode, CompanyInfo } from "@/lib/company-store";
import { fetchCompanyInfo } from "@/lib/company-data";
import { buttonClass, Field, inputClass } from "./ui";

export default function CompanyCodeEntry({title,action,existing,onOpen}:{title:string;action:string;existing:string[];onOpen:(info:CompanyInfo)=>void}){
 const [code,setCode]=useState(""),[info,setInfo]=useState<CompanyInfo|null>(null),[loading,setLoading]=useState(false),[error,setError]=useState("");
 useEffect(()=>{let active=true;setInfo(null);setError("");setLoading(false);if(!companyCode(code))return;setLoading(true);const timer=setTimeout(()=>{fetchCompanyInfo(code).then(p=>{if(active)setInfo(p);}).catch(e=>{if(active)setError(String(e));}).finally(()=>{if(active)setLoading(false);});},300);return()=>{active=false;clearTimeout(timer);};},[code]);
 const duplicate=info&&existing.includes(info.code);
 return <div><h3 className="text-lg font-semibold">{title}</h3><p className="mt-1 text-sm text-slate-500">只输入代码，自动识别名称、行情及可取得的分红信息。</p><div className="mt-4 flex flex-wrap items-end gap-3"><Field label="股票代码"><input className={inputClass} value={code} maxLength={20} placeholder="如 600519 或 000001" onChange={e=>setCode(e.target.value)}/></Field><button disabled={!info||loading||info.code!==companyCode(code)} className={buttonClass} onClick={()=>{if(info&&info.code===companyCode(code))onOpen(info);}}>{duplicate?"打开已有记录":action}</button></div>{loading&&<p role="status" className="mt-3 text-xs text-emerald-700">正在识别公司与数据来源…</p>}{code.trim()&&!companyCode(code)&&<p className="mt-3 text-xs text-slate-500">请输入有效A股股票代码，保留开头的0。</p>}{error&&<p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}{info&&<div className="mt-4 rounded-xl bg-emerald-50 p-4"><p className="font-semibold">{info.name} · {info.code}</p><p className="mt-2 text-sm text-slate-600">{info.industry||"行业待核实"} · ¥{info.quote.price.toFixed(2)} · 动态PE {info.quote.pe==null?"未知":info.quote.pe.toFixed(2)} · PB {info.quote.pb==null?"未知":info.quote.pb.toFixed(2)}</p><p className="mt-2 text-xs text-slate-400">{info.quoteSource} · 报价 {new Date(info.quote.quote_time).toLocaleString("zh-CN")}</p>{duplicate&&<p className="mt-2 text-xs text-emerald-800">同一代码已有档案，会打开已有记录并保留研究内容。</p>}</div>}</div>;
}
