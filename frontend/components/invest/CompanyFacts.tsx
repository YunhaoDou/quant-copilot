"use client";
import { useLiveQuotes, LiveQuote } from "@/lib/live-market";
import { CompanyProfile } from "@/lib/company-store";
import { Metric } from "./ui";
export function currentDividend(c:CompanyProfile,q?:LiveQuote){const d=c.info?.dividend;return q&&d?.verified&&d.cashPerShare!=null&&d.asOf===q.quote_time.slice(0,10)?d.cashPerShare/q.price*100:null;}
export default function CompanyFacts({company:c}:{company:CompanyProfile}){
 const {data,error}=useLiveQuotes([c.code]),q=data?.quotes.find(r=>r.code===c.code),yieldPct=currentDividend(c,q);
 return <div><p className="text-xs leading-6 text-slate-500">{c.info?.industry||"行业未知"}{c.info?.industrySource?` · ${c.info.industrySource}`:""}</p><div className="mt-3 grid grid-cols-2 gap-3"><Metric label="真实现价" value={q?`¥${q.price.toFixed(2)}`:"未知"}/><Metric label="动态PE / PB" value={q?`${q.pe?.toFixed(2)??"未知"} / ${q.pb?.toFixed(2)??"未知"}`:"未知"}/><Metric label="已实施税前股息率" value={yieldPct!=null?`${yieldPct.toFixed(2)}%`:"未知"}/><Metric label="财务质量" value="待研究" hint="未自动生成质量分"/></div><p className="mt-3 text-xs leading-6 text-slate-400">报价：{data?.provider||"腾讯公开行情"} · {q?new Date(q.quote_time).toLocaleString("zh-CN"):error?"暂不可用":"正在读取"}。股息率：{c.info?.dividend.source||"等待已实施分红记录"} · 口径截至 {c.info?.dividend.asOf||"未知"}。</p><p className="mt-1 text-xs leading-6 text-amber-800">{c.info?.dividend.note||"资料缺失显示未知，不要求手填客观数据。"}{q&&c.info?.dividend.asOf!==q.quote_time.slice(0,10)?" 分红口径日期与报价不一致，正在更新资料，暂不显示息率。":""}</p></div>;
}
