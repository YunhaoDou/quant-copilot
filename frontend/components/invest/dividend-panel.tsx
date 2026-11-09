"use client";

import { useEffect, useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import type { PersonalInvestmentState } from "@/lib/personal-investment";
import { upsertCompany } from "@/lib/company-store";
import { fetchCompanyInfo, useCompanyProfiles } from "@/lib/company-data";
import { navigateInvestmentView } from "@/lib/invest-navigation";
import CompanyFacts from "./CompanyFacts";
import CompanyKline from "./CompanyKline";
import { marketApiUrl, useLiveQuotes } from "@/lib/live-market";
import { buttonClass, Card, Field, inputClass, Metric, secondaryButtonClass } from "./ui";

type DividendQuality = {
  status: "supported" | "review" | "financial" | "unknown" | "risk";
  fiscalYear: number | null;
  noticeDate: string | null;
  payoutPct: number | null;
  fcfCover: number | null;
  debtPct: number | null;
  historicalYield: number | null;
  operatingCash: number | null;
  monetaryFunds: number | null;
  deductedProfits: (number | null)[];
  flags: string[];
  financialIndustry: boolean;
};
const qualityLabels: Record<DividendQuality["status"], string> = {
  supported: "财务证据支持", review: "需复核", financial: "金融股单独核验",
  unknown: "财务数据不足", risk: "派息风险",
};

function QualityDetails({ quality }: { quality?: DividendQuality }) {
  if (!quality) return <p className="mt-3 text-xs text-slate-500">此快照使用旧策略，请重新扫描以核验财务。</p>;
  const percent = (value: number | null) => value === null ? "未知" : `${value.toFixed(1)}%`;
  const amount = (value: number | null) => value === null ? "未知" : `${(value / 1e8).toFixed(2)} 亿元`;
  return <div className="mt-4 border-t border-slate-100 pt-3 text-xs leading-6 text-slate-700">
    <p className="font-semibold">{qualityLabels[quality.status]}</p>
    <p>历史中位股息率（扫描价） {percent(quality.historicalYield)} · 同财年估算派息率 {percent(quality.payoutPct)}</p>
    {!quality.financialIndustry && <p>自由现金流覆盖 {quality.fcfCover === null ? "未知" : `${quality.fcfCover.toFixed(2)} 倍`} · 资产负债率 {percent(quality.debtPct)}</p>}
    {!quality.financialIndustry && <p>经营现金流 {amount(quality.operatingCash)} · 货币资金 {amount(quality.monetaryFunds)}</p>}
    {!quality.financialIndustry && quality.deductedProfits.length > 0 && <p>近年扣非归母利润（由近到远） {quality.deductedProfits.map(amount).join(" / ")}</p>}
    <p className="text-slate-500">东方财富年报摘要 · {quality.fiscalYear ? `${quality.fiscalYear} 财年` : "财年未知"}{quality.noticeDate && ` · 利润表披露 ${quality.noticeDate}`}</p>
    {quality.flags.length > 0 && <ul className="mt-1 list-disc pl-4 text-amber-800">{quality.flags.map(flag => <li key={flag}>{flag}</li>)}</ul>}
    {quality.financialIndustry && <p>结合资本充足率、偿付能力及监管约束复核。</p>}
  </div>;
}

type Stock = {code:string;name:string;sector:string;category:string;price:number;dividendYield:number;cashPerShare:number;consecutiveYears:number;lowPosition:number;quality?:DividendQuality;signal:string;quoteTime:string;history:number[];historyDates:string[];historyThrough:string;drawdown:number;dividendRecords:{exDate:string;cashPerShare:number;reportDate:string}[]};
type Board = {strategyVersion?:number;status:string;progress:string;tradeDate?:string;updatedAt?:string;stocks:Stock[];scanned:number;preselected:number;checked:number;failures:string[];notes?:string[];source?:string;config?:Record<string,number>};
const signalName = (s:string) => s === "stage" ? "低位观察" : s === "wait" ? "位置偏高" : "持续观察";

export default function DividendPanel({state,setState}:{state:PersonalInvestmentState;setState:Dispatch<SetStateAction<PersonalInvestmentState>>}) {
  const [actionError,setActionError]=useState(""),[joining,setJoining]=useState(false);
  async function join(code:string,research=false){setJoining(true);setActionError("");try{const info=await fetchCompanyInfo(code);setState(s=>research?upsertCompany(upsertCompany(s,info,"watch","红利看板"),info,"research"):upsertCompany(s,info,"watch","红利看板"));if(research)navigateInvestmentView("research",code);}catch(e){setActionError(String(e));}finally{setJoining(false);}}
  const [data,setData]=useState<Board|null>(null),[error,setError]=useState(""),[category,setCategory]=useState("全部"),[sector,setSector]=useState("全部"),[onlyLow,setOnlyLow]=useState(false),[onlySupported,setOnlySupported]=useState(false),[selected,setSelected]=useState(""),[view,setView]=useState("分类看板");
  useEffect(()=>{ if(new URLSearchParams(window.location.search).get("cards")==="1")setView("红利筛选摘要"); },[]);
  useEffect(()=>{
    let active=true;let timer:ReturnType<typeof setTimeout>;const controller=new AbortController();
    async function poll(){let running=false;try{const r=await fetch(`${marketApiUrl()}/dividends`,{signal:controller.signal,cache:"no-store"});const p=await r.json();if(!r.ok)throw new Error(p.detail||"扫描状态读取失败");if(active){setData(p);setError("");running=p.status==="running";}}catch(e){if(active&&!controller.signal.aborted)setError(String(e));}finally{if(active)timer=setTimeout(poll,running?2000:15000);}}
    poll();return()=>{active=false;controller.abort();clearTimeout(timer);};
  },[]);
  async function scan(){setError("");try{const r=await fetch(`${marketApiUrl()}/dividends/scan`,{method:"POST"});const p=await r.json();if(!r.ok)throw new Error(p.detail||"无法启动扫描");setData(old=>({...old!,status:"running",progress:p.progress,stocks:old?.stocks||[],failures:old?.failures||[],scanned:old?.scanned||0,preselected:old?.preselected||0,checked:0}));}catch(e){setError(String(e));}}
  const quotes=useLiveQuotes([...(data?.stocks.slice(0,90).map(s=>s.code)||[]),...(selected?[selected]:[])]);
  const liveStocks=useMemo(()=> (data?.stocks||[]).map(s=>{
    const quote=quotes.data?.quotes.find(q=>q.code===s.code);
    if(!quote)return s;
    const d=state.companies?.[s.code]?.info?.dividend;
    const cash=d?.verified&&d.cashPerShare!=null&&d.asOf===quote.quote_time.slice(0,10)?d.cashPerShare:s.cashPerShare;
    const min=Math.min(...s.history),max=Math.max(...s.history),lowPosition=max===min?50:Math.max(0,Math.min(100,(quote.price-min)/(max-min)*100)),dividendYield=cash/quote.price*100;
    return {...s,cashPerShare:cash,price:quote.price,dividendYield,lowPosition,quoteTime:quote.quote_time,drawdown:(quote.price/max-1)*100,signal:lowPosition<=(data?.config?.dividend_low_position_pct??35)?"stage":lowPosition>=(data?.config?.dividend_high_position_pct??70)?"wait":"watch"};
  }),[data,quotes.data,state.companies]);
  const categories=Array.from(new Set(liveStocks.map(s=>s.category))).sort();
  const industries=Array.from(new Set(liveStocks.filter(s=>category==="全部"||s.category===category).map(s=>s.sector))).sort();
  const filtered=liveStocks.filter(s=>(category==="全部"||s.category===category)&&(sector==="全部"||s.sector===sector)&&(!onlyLow||s.signal==="stage")&&(!onlySupported||s.quality?.status==="supported"));
  const ranked=categories.flatMap(c=>filtered.filter(s=>s.category===c).slice(0,data?.config?.dividend_per_category||8));
  const chosen=ranked.find(s=>s.code===selected)||ranked[0];
  const chosenCompany=chosen?state.companies?.[chosen.code]:undefined;
  useCompanyProfiles(chosenCompany?[chosenCompany.code]:[],setState);
  useEffect(()=>{if(!chosen?.code)return;let active=true;fetchCompanyInfo(chosen.code).then(info=>{if(active)setState(s=>upsertCompany(s,info,"view","红利看板"));}).catch(e=>{if(active)setActionError(String(e));});return()=>{active=false;};},[chosen?.code,setState]);
  const avg=ranked.length?ranked.reduce((n,s)=>n+s.dividendYield,0)/ranked.length:0;
  function exportPNG(){
    if(!ranked.length)return;
    const canvas=document.createElement("canvas");canvas.width=1080;canvas.height=1440;const c=canvas.getContext("2d");if(!c)return;
    c.fillStyle="#fffdfb";c.fillRect(0,0,1080,1440);c.fillStyle="#913045";c.fillRect(0,0,1080,250);c.fillStyle="white";c.font="32px sans-serif";c.fillText("攒股躺平日记 · 真实数据",60,75);c.font="bold 54px sans-serif";c.fillText("高股息观察看板",60,150);c.font="26px sans-serif";c.fillText(`${data?.tradeDate} · ${category} · 分类规则排序`,60,210);
    ranked.slice(0,8).forEach((s,i)=>{const y=320+i*118;c.fillStyle=i%2?"#f7f1ed":"#fffdfb";c.fillRect(40,y-45,1000,108);c.fillStyle="#242323";c.font="bold 30px sans-serif";c.fillText(`${i+1}. ${s.name}`,65,y);c.font="21px sans-serif";c.fillStyle="#746f6b";c.fillText(`${s.code} · ${s.sector}`,65,y+35);c.fillStyle="#913045";c.font="bold 29px sans-serif";c.fillText(`${s.dividendYield.toFixed(2)}%`,590,y);c.fillText(`位置${s.lowPosition.toFixed(0)}%`,810,y);});
    c.fillStyle="#746f6b";c.font="23px sans-serif";c.fillText("已实施税前现金分红；财务分层用于候选研究。",60,1340);c.fillText("各标的报价时间以看板为准，发布前复核公司公告。",60,1380);
    const a=document.createElement("a");a.download=`红利观察-${data?.tradeDate}-${category}.png`;a.href=canvas.toDataURL("image/png");a.click();
  }
  return <div className="space-y-5"><Card className="!bg-[#692131] !text-white"><div className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-xs tracking-widest text-rose-100/70">攒股躺平日记 · 红利研究</p><h2 className="mt-2 text-2xl font-semibold">高股息观察看板</h2><p className="mt-2 text-sm text-rose-100/70">先核对历史派息和财务覆盖，再看价格位置与公告证据。</p></div><span className="rounded-full border border-white/20 px-3 py-2 text-xs">真实全A股扫描 · 无演示回退</span></div></Card>
    <Card><div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="font-semibold">{data?.progress||"正在连接扫描服务…"}</h3><p className="mt-1 text-xs text-slate-400">{data?.updatedAt?`上次完整扫描：${new Date(data.updatedAt).toLocaleString("zh-CN")} · 行情日 ${data.tradeDate}`:"首次请启动全市场扫描，扫描期间可查看进度。"}</p></div><button className={buttonClass} disabled={data?.status==="running"} onClick={scan}>{data?.status==="running"?"正在扫描…":"扫描 / 更新真实数据"}</button></div>{error&&<p className="mt-3 text-sm text-red-700">{error}</p>}{data?.status==="error"&&<p className="mt-3 text-sm text-red-700">本次扫描失败。下方若有数据，仍是上次成功扫描，不能视作已更新。</p>}<div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4"><Metric label="全A股覆盖" value={String(data?.scanned||0)}/><Metric label="红利初筛" value={String(data?.preselected||0)}/><Metric label="日线核验" value={String(data?.checked||0)}/><Metric label="当前分类入选 / 平均息率" value={`${ranked.length} / ${avg.toFixed(2)}%`}/></div></Card>
    <Card><div className="grid gap-3 sm:grid-cols-4"><Field label="行业大类"><select className={inputClass} value={category} onChange={e=>{setCategory(e.target.value);setSector("全部");}}><option>全部</option>{categories.map(c=><option key={c}>{c}</option>)}</select></Field><Field label="细分行业"><select className={inputClass} value={sector} onChange={e=>setSector(e.target.value)}><option>全部</option>{industries.map(s=><option key={s}>{s}</option>)}</select></Field><Field label="展示方式"><select className={inputClass} value={view} onChange={e=>setView(e.target.value)}><option>分类看板</option><option>红利筛选摘要</option></select></Field><div className="flex items-end gap-3"><label className="text-sm"><input type="checkbox" checked={onlyLow} onChange={e=>setOnlyLow(e.target.checked)}/> 仅低位观察</label><button className={secondaryButtonClass} disabled={!ranked.length} onClick={exportPNG}>导出PNG</button></div></div><p className="mt-3 text-xs text-slate-400">列表为标注日期的扫描筛选快照，点击公司后查看统一实时资料与K线。分类排名基于上次完整扫描评分。最高评分的前90只候选另做30秒报价刷新；其他标的显示各自扫描时间，不混称全部实时。</p>{quotes.error&&<p className="mt-2 text-xs text-amber-700">报价刷新失败：{quotes.error}，保留已标注时间的扫描快照。</p>}</Card>
    {data?.stocks.length && !data.strategyVersion ? <Card>当前展示的是旧策略快照。重新扫描后，分类列表会按新版财务证据排序。</Card> : null}
    {data?.strategyVersion === 2 && <Card><label className="flex items-center gap-2 text-sm font-medium"><input type="checkbox" checked={onlySupported} onChange={e=>setOnlySupported(e.target.checked)} />只看财务证据支持</label><p className="mt-2 text-xs leading-6 text-slate-500">保留未知与风险候选供复核。价格位置只作辅助观察。</p></Card>}
    {!ranked.length&&<Card>尚无符合条件的已核验标的。请先扫描真实数据；数据不足时不生成研究结论。</Card>}
    {ranked.length>0&&view==="分类看板"&&<div className="grid items-start gap-5 xl:grid-cols-[1.6fr_1fr]"><Card><h3 className="text-lg font-semibold">分类优选 · 每类最多8只</h3><div className="mt-4 overflow-x-auto"><table className="w-full min-w-[720px] text-left text-sm"><thead className="border-b text-xs text-slate-400"><tr>{["公司","分类/行业","财务核验","连续派息","近12月息率","现价","价格位置","状态"].map(v=><th className="py-3" key={v}>{v}</th>)}</tr></thead><tbody>{ranked.map(s=><tr key={s.code} onClick={()=>setSelected(s.code)} className="cursor-pointer border-b border-slate-100 hover:bg-rose-50"><td className="py-3"><button className="text-left" onClick={()=>setSelected(s.code)}><strong>{s.name}</strong><small className="block text-slate-400">{s.code}</small></button></td><td className="text-xs">{s.category}<br/>{s.sector}</td><td className="text-xs">{s.quality ? qualityLabels[s.quality.status] : "旧策略"}</td><td>{s.consecutiveYears}年</td><td className="font-semibold text-[#913045]">{s.dividendYield.toFixed(2)}%</td><td>{s.price.toFixed(2)}</td><td>{s.lowPosition.toFixed(0)}%</td><td className="text-xs">{signalName(s.signal)}</td></tr>)}</tbody></table></div></Card>{chosen&&<Card><h3 className="text-xl font-semibold">{chosen.name} <span className="text-sm font-normal text-slate-400">{chosen.code}</span></h3><p className="mt-2 text-xs text-slate-400">报价时间 {new Date(chosen.quoteTime).toLocaleString("zh-CN")}</p><div className="mt-4 flex flex-wrap gap-2"><button disabled={joining} className={buttonClass} onClick={()=>state.companies?.[chosen.code]?.inWatchlist?navigateInvestmentView("watchlist",chosen.code):join(chosen.code)}>{state.companies?.[chosen.code]?.inWatchlist?"查看观察池":"加入观察池"}</button><button disabled={joining} className={secondaryButtonClass} onClick={()=>join(chosen.code,true)}>{state.companies?.[chosen.code]?.inWatchlist?"打开研究":"加入并研究"}</button></div><QualityDetails quality={chosen.quality}/>{chosenCompany&&<div className="mt-4"><CompanyFacts company={chosenCompany}/></div>}<div className="mt-5"><CompanyKline code={chosen.code}/></div><p className="mt-3 text-xs text-slate-400">下面为扫描时保存的分红记录；当前公司资料、研究区间及失效条件使用统一公司档案。</p><h4 className="mt-5 font-medium">已实施分红记录</h4>{chosen.dividendRecords.slice(0,6).map((r,i)=><div key={i} className="flex justify-between border-b py-2 text-xs"><span>{r.exDate}</span><span>每股 ¥{r.cashPerShare.toFixed(3)}</span></div>)}</Card>}</div>}
    {view==="红利筛选摘要"&&ranked.length>0&&<div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{ranked.map(s=><Card key={s.code}><p className="text-xs text-[#913045]">{s.category} · {s.sector}</p><h3 className="mt-2 text-xl font-semibold">{s.name}</h3><p className="mt-3 text-3xl font-semibold text-[#913045]">{s.dividendYield.toFixed(2)}%</p><p className="mt-2 text-sm text-slate-500">窗口内连续派息 {s.consecutiveYears} 年 · 价格位置 {s.lowPosition.toFixed(0)}%</p><p className="mt-3 text-sm">规则状态：{signalName(s.signal)}</p><div className="mt-4 flex flex-wrap gap-2"><button disabled={joining} className={secondaryButtonClass} onClick={()=>state.companies?.[s.code]?.inWatchlist?navigateInvestmentView("watchlist",s.code):join(s.code)}>{state.companies?.[s.code]?.inWatchlist?"查看观察池":"加入观察池"}</button><button disabled={joining} className={secondaryButtonClass} onClick={()=>{setSelected(s.code);setView("分类看板");}}>查看公司与K线</button></div><QualityDetails quality={s.quality}/><p className="mt-3 text-xs leading-6 text-slate-500">治理线索：在公司公告核对实际控制人、第一大股东持股和分红政策。股权性质不参与排名。</p><p className="mt-3 text-xs text-slate-400">{new Date(s.quoteTime).toLocaleString("zh-CN")}</p></Card>)}</div>}
    {actionError&&<Card><p role="alert" className="text-sm text-red-700">公司资料读取失败：{actionError}</p><p className="mt-2 text-xs text-slate-400">未创建空白或重复档案，请稍后重试。</p></Card>}<Card><h3 className="font-semibold">口径与异常</h3>{data?.notes?.map(n=><p className="mt-2 text-xs leading-6 text-slate-500" key={n}>{n}</p>)}{data?.failures?.length? <details className="mt-3 text-xs text-amber-700"><summary>查看{data.failures.length}项排除 / 数据异常</summary><div className="mt-2 max-h-52 overflow-auto">{data.failures.map((f,i)=><p className="py-1" key={i}>{f}</p>)}</div></details>:null}<p className="mt-3 text-xs text-slate-400">从另一份quant-copilot迁入分类规则与红利筛选摘要流程。高股息不等于低风险；数据以公司公告复核，不构成投资建议。</p></Card>
  </div>;
}
