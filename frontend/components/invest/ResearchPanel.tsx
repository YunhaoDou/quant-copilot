"use client";
import { useEffect, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { PersonalInvestmentState } from "@/lib/personal-investment";
import { CompanyInfo, CompanyResearch, openCompanyResearch, patchCompanyResearch, upsertCompany } from "@/lib/company-store";
import { useCompanyProfiles } from "@/lib/company-data";
import { INVESTMENT_VIEW_EVENT, navigateInvestmentView } from "@/lib/invest-navigation";
import { buttonClass, Card, Empty, Field, inputClass, secondaryButtonClass } from "./ui";
import CompanyCodeEntry from "./CompanyCodeEntry";
import CompanyFacts from "./CompanyFacts";
import CompanyKline from "./CompanyKline";
import WorkspaceTabs from "./WorkspaceTabs";
import ResearchLabModule from "./modules/ResearchLabModule";
import AiResearchModule from "./modules/AiResearchModule";
import CompanyArchiveNotice from "./CompanyArchiveNotice";
type Props={state:PersonalInvestmentState;setState:Dispatch<SetStateAction<PersonalInvestmentState>>};

export default function ResearchPanel({state,setState}:Props){
 const [code,setCode]=useState<string|undefined>();
 useEffect(()=>{const sync=()=>{const company=new URLSearchParams(window.location.search).get("company");if(company)setCode(company);};sync();window.addEventListener(INVESTMENT_VIEW_EVENT,sync);window.addEventListener("popstate",sync);return()=>{window.removeEventListener(INVESTMENT_VIEW_EVENT,sync);window.removeEventListener("popstate",sync);};},[]);
 useEffect(()=>{setCode(previous=>previous||Object.values(state.companies||{}).find(c=>c.research.opened)?.code);},[state.companies]);
 function selectCompany(value:string){setCode(value);const url=new URL(window.location.href);url.searchParams.set("company",value);window.history.replaceState({},"",url);}

 return <WorkspaceTabs label="个股研究功能" tabs={[{id:"thesis",label:"公司论证",content:<CompanyResearchEditor state={state} setState={setState} companyCode={code} onCompany={selectCompany}/>},{id:"diagnosis",label:"技术诊断与追问",content:<ResearchLabModule section="股票诊断" initialCode={code}/>},{id:"ai-note",label:"AI结构化笔记",content:<AiResearchModule initialSymbol={code}/>}]} />;
}

function CompanyResearchEditor({state,setState,onCompany,companyCode}:Props&{onCompany:(code:string)=>void;companyCode?:string}){
 const list=Object.values(state.companies||{}).filter(c=>c.research.opened),[selected,setSelected]=useState<string|null>(companyCode||null),[message,setMessage]=useState(""),[range,setRange]=useState({low:"",high:""}),[rangeError,setRangeError]=useState("");
 const c=(selected?state.companies?.[selected]:null)||list[0];
 useEffect(()=>{if(c)onCompany(c.code);},[c?.code]);
 const errors=useCompanyProfiles(c?[c.code]:[],setState);
 useEffect(()=>{function sync(){const code=new URLSearchParams(window.location.search).get("company");if(code){setSelected(code);setState(s=>openCompanyResearch(s,code));}}sync();window.addEventListener(INVESTMENT_VIEW_EVENT,sync);window.addEventListener("popstate",sync);return()=>{window.removeEventListener(INVESTMENT_VIEW_EVENT,sync);window.removeEventListener("popstate",sync);};},[]);
 useEffect(()=>{setRange({low:c?.research.targetLow?.toString()||"",high:c?.research.targetHigh?.toString()||""});setRangeError("");},[c?.code,c?.research.targetLow,c?.research.targetHigh]);
 function open(info:CompanyInfo){const exists=state.companies?.[info.code]?.research.opened;setState(s=>upsertCompany(s,info,"research"));setSelected(info.code);setMessage(exists?"已打开已有研究，未重复创建。":"已打开公司研究。文本自动保存，区间与失效条件共享到观察池。");}
 function update(field:keyof CompanyResearch,value:string){if(c)setState(s=>patchCompanyResearch(s,c.code,{[field]:value}));}
 function saveRange(){if(!c)return;const low=Number(range.low),high=Number(range.high);if(!range.low||!range.high||!Number.isFinite(low)||!Number.isFinite(high)||low<=0||high<low){setRangeError("请填写有效正数，且区间上限不得低于下限。");return;}setState(s=>patchCompanyResearch(s,c.code,{targetLow:low,targetHigh:high,legacyRangeConflict:false}));setRangeError("");setMessage("研究区间已保存到同一公司档案，观察池同步显示。");}
 return <div className="space-y-5"><Card><CompanyCodeEntry title="按代码打开个股研究" action="打开公司研究" existing={list.map(c=>c.code)} onOpen={open}/>{message&&<p role="status" className="mt-3 text-sm text-emerald-800">{message}</p>}</Card><CompanyArchiveNotice archive={state.companyLegacyArchive}/><div className="grid items-start gap-5 xl:grid-cols-[260px_1fr]"><Card><h2 className="font-semibold">研究公司 · {list.length}</h2><div className="mt-3 space-y-2">{list.map(item=><button key={item.code} className={`w-full rounded-xl border p-3 text-left ${c?.code===item.code?"border-emerald-400 bg-emerald-50":"border-slate-200"}`} onClick={()=>{setSelected(item.code);setMessage("");}}><strong className="text-sm">{item.name}</strong><small className="mt-1 block text-slate-400">{item.code}</small></button>)}{!list.length&&<Empty>输入代码，或从观察池打开研究。</Empty>}</div></Card>
  {!c?<Card><Empty>每个证券代码只有一份公司档案，研究内容会自动保留。</Empty></Card>:<Card><div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-2xl font-semibold">{c.name} · {c.code}</h2><p className="mt-2 text-xs text-slate-400">文本自动保存 · 最近研究更新 {c.research.updatedAt?new Date(c.research.updatedAt).toLocaleString("zh-CN"):"尚未填写"}</p></div><button className={secondaryButtonClass} onClick={()=>{setState(s=>({...s,companies:{...s.companies,[c.code]:{...s.companies![c.code],inWatchlist:true}}}));navigateInvestmentView("watchlist",c.code);}}>{c.inWatchlist?"返回观察池":"加入观察池"}</button></div><div className="mt-5"><CompanyFacts company={c}/></div>{errors[c.code]&&<p className="mt-3 text-xs text-amber-800">资料更新暂不可用，保留原研究内容；客观数据缺失不会用手工数值替代。</p>}<div className="mt-5 border-t pt-5"><CompanyKline code={c.code}/></div>
  <div className="mt-6 rounded-2xl bg-emerald-50 p-4"><h3 className="font-semibold">研究区间与跟踪条件 · 共享给观察池</h3><p className="mt-2 text-xs leading-6 text-slate-500">区间是你的研究假设，系统不能仅凭股票代码推断。当前报价口径下填写，跨除权事件需复核。</p>{c.research.legacyRangeConflict&&<p className="mt-3 text-sm text-amber-800">历史重复条目的研究区间不一致，原值都在迁移存档中。请核对后重新确认，系统未替你选择。</p>}<div className="mt-3 grid gap-3 sm:grid-cols-2"><Field label="研究区间下限"><input className={inputClass} type="number" min="0" step="0.01" value={range.low} onChange={e=>setRange({...range,low:e.target.value})}/></Field><Field label="研究区间上限"><input className={inputClass} type="number" min="0" step="0.01" value={range.high} onChange={e=>setRange({...range,high:e.target.value})}/></Field><Field label="跟踪状态"><select className={inputClass} value={c.trackingStatus} onChange={e=>setState(s=>({...s,companies:{...s.companies,[c.code]:{...s.companies![c.code],trackingStatus:e.target.value as "观察"|"排除"}}}))}><option>观察</option><option>排除</option></select></Field><Field label="风险标签 / 已知风险"><input className={inputClass} value={c.riskTags} onChange={e=>setState(s=>({...s,companies:{...s.companies,[c.code]:{...s.companies![c.code],riskTags:e.target.value}}}))}/></Field></div>{rangeError&&<p role="alert" className="mt-3 text-sm text-red-700">{rangeError}</p>}<div className="mt-3 flex flex-wrap gap-2"><button className={buttonClass} onClick={saveRange}>保存研究区间</button><button className={secondaryButtonClass} onClick={()=>{setState(s=>patchCompanyResearch(s,c.code,{targetLow:null,targetHigh:null,legacyRangeConflict:false}));setRange({low:"",high:""});setRangeError("");}}>清空研究区间</button></div></div>
  <div className="mt-5 grid gap-4 lg:grid-cols-2">{([['businessModel','商业模式','谁付钱、为什么付钱，公司如何产生现金流？'],['financialTrend','财务趋势与证据','记录财报来源、日期、收入、利润及现金流，缺项注明待核实。'],['valuationThesis','估值情景与假设','悲观、中性、乐观假设；与上方结构化研究区间对应。'],['catalysts','潜在催化剂','来源、事件时间及待验证条件。'],['bearCase','反方观点','最有力的看空证据及风险。'],['invalidation','逻辑失效条件','出现哪些可观察事实时，必须重估或退出？会同步到观察池。']] as const).map(([key,label,placeholder])=><Field key={key} label={label}><textarea className={`${inputClass} min-h-36 resize-y ${key==="invalidation"?"border-amber-300":""}`} value={c.research[key]} placeholder={placeholder} onChange={e=>update(key,e.target.value)}/></Field>)}</div>
  </Card>}
 </div></div>;
}
