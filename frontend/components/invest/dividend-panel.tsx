"use client";

import {useReadResource,useDebouncedValue} from "@/lib/read-resource";
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
  ocfCover?: number | null;
  cashProfitRatio?: number | null;
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

type BondBenchmark = { date: string; yieldPct: number; previousDate: string | null; changeBp: number | null };

type ScreeningStatus = "pass" | "fail" | "unknown" | "manual";
type ScreeningFilter = ScreeningStatus | "all" | "supported";
type Screening = {
  status: ScreeningStatus;
  checks: { label: string; value: number | null; unit: string; minimum: number; maximum: number | null; passed: boolean | null }[];
};
const screeningLabels: Record<ScreeningStatus, string> = {
  pass: "量化通过", fail: "未达标", unknown: "数据不足", manual: "需人工复核",
};

type Stock = {screening?:Screening;pe?:number|null;pb?:number|null;annualCashPerShare?:{year:number;cash:number}[];code:string;name:string;sector:string;category:string;price:number|null;dividendYield:number|null;cashPerShare:number;consecutiveYears:number;lowPosition:number|null;historyLow?:number|null;historyHigh?:number|null;quality?:DividendQuality;signal:string;quoteTime:string|null;history:number[];historyDates:string[];historyThrough:string;drawdown:number|null;dividendRecords:{exDate:string;cashPerShare:number;reportDate:string}[]};
type Board = {snapshot_version?:string;total?:number;matched?:number;passing_count?:number;failure_count?:number;average_yield?:number|null;categories?:string[];industries?:string[];selected_stock?:Stock|null;benchmark?:BondBenchmark|null;strategyVersion?:number;status:string;progress:string;tradeDate?:string;updatedAt?:string;stocks:Stock[];scanned:number;preselected:number;checked:number;failures:string[];notes?:string[];source?:string;config?:Record<string,number>};
function FrameworkDetails({ stock, benchmark }: { stock: Stock; benchmark?: BondBenchmark | null }) {
  const quality = stock.quality;
  const multiple = (value?: number | null) => value != null ? `${value.toFixed(2)} 倍` : "未知";
  const pe = stock.pe != null && stock.pe > 0 ? multiple(stock.pe) : "未知或亏损不适用";
  const pb = stock.pb != null && stock.pb > 0 ? multiple(stock.pb) : "未知或不适用";
  const spread = benchmark && quality?.historicalYield != null
    ? `${(quality.historicalYield - benchmark.yieldPct).toFixed(2)} 个百分点`
    : "未知";
  const rows = [
    ["股息率", `近12月已实施税前股息率 ${fixed(stock.dividendYield,2)}%。较高读数需核对特别派息、股价下跌和税后实际收益。`],
    ["支付率与稳定性", `连续派息 ${stock.consecutiveYears} 年。完整除权年度每股派息记录：${stock.annualCashPerShare?.map(({year,cash}) => `${year} 年 ${cash > 0 ? `¥${cash.toFixed(3)}` : "无记录"}`).join(" / ") || "未知"}。分红承诺及削减原因查公告。`],
    ["盈利与现金流", quality?.financialIndustry ? "金融股请核对资本充足率或偿付能力。" : `经营现金流 / 估算派息 ${multiple(quality?.ocfCover)}，经营现金流 / 归母净利 ${multiple(quality?.cashProfitRatio)}。再与扣资本开支后的覆盖和多期盈利对照。`],
    ["估值", `东方财富扫描时动态PE ${pe}、PB ${pb}。历史估值分位暂缺。周期行业宜核对中周期盈利，金融股结合PB、ROE和资产质量。`],
    ["行业与基本面", `${stock.sector}。从公告核对竞争格局、需求及定价、资本开支、治理、股权质押与分红政策。行业或股东身份仅作背景。`],
    ["利率与股债差", benchmark
      ? `中债10年期国债 ${benchmark.yieldPct.toFixed(4)}%（${benchmark.date}）。历史中位股息率减国债收益率为 ${spread}。${benchmark.previousDate && benchmark.changeBp != null ? `较 ${benchmark.previousDate} 变动 ${benchmark.changeBp.toFixed(2)} 基点。` : ""} 股债差用于比较收益口径，股票还承担股价和削减分红风险。`
      : "同口径国债收益率未知，股债差留空。"],
  ];
  return <details className="mt-4 border-t border-slate-100 pt-3 text-xs leading-6 text-slate-700">
    <summary className="cursor-pointer font-semibold text-slate-900">展开六维评估</summary>
    <dl className="mt-2 divide-y divide-slate-100">{rows.map(([label, evidence]) =>
      <div className="py-2" key={label}><dt className="font-semibold">{label}</dt><dd>{evidence}</dd></div>
    )}</dl>
  </details>;
}
function ScreeningDetails({ screening }: { screening?: Screening }) {
  if (!screening) return null;
  return <details className="mt-3 border-t border-slate-100 pt-3 text-xs leading-6 text-slate-700">
    <summary className="cursor-pointer font-semibold text-slate-900">自动筛选 · {screeningLabels[screening.status]}</summary>
    <ul className="mt-2 divide-y divide-slate-100">
      {screening.checks.map(({ label, value, unit, minimum, maximum, passed }) => (
        <li className="flex flex-wrap justify-between gap-x-3 py-1" key={label}>
          <span>{label} <span className="text-slate-500">（{maximum === null ? `≥${minimum}` : `${minimum}–${maximum}`}{unit}）</span></span>
          <span className={passed === true ? "text-emerald-700" : passed === false ? "text-amber-800" : "text-slate-500"}>
            {value === null ? "未知" : `${Number(value.toFixed(2))}${unit} · ${passed ? "通过" : "未通过"}`}
          </span>
        </li>
      ))}
    </ul>
    <p className="mt-2 text-slate-500">按扫描快照判定，另需核对历史估值、行业基本面和治理。分红风险或其他财务复核项见上方财务分层。</p>
  </details>;
}
const fixed=(v:number|null|undefined,d=2)=>v!=null&&Number.isFinite(v)?v.toFixed(d):"未知";
const signalName = (s:string) => s === "unknown" ? "数据不足" : s === "stage" ? "低位观察" : s === "wait" ? "位置偏高" : "持续观察";

export default function DividendPanel({state,setState}:{state:PersonalInvestmentState;setState:Dispatch<SetStateAction<PersonalInvestmentState>>}) {
  const [actionError,setActionError]=useState(""),[joining,setJoining]=useState(false);
  async function join(code:string,research=false){setJoining(true);setActionError("");try{const info=await fetchCompanyInfo(code);setState(s=>research?upsertCompany(upsertCompany(s,info,"watch","红利看板"),info,"research"):upsertCompany(s,info,"watch","红利看板"));if(research)navigateInvestmentView("research",code);}catch(e){setActionError(String(e));}finally{setJoining(false);}}
  const [scanError,setScanError]=useState(""),[category,setCategory]=useState("全部"),[sector,setSector]=useState("全部"),[onlyLow,setOnlyLow]=useState(false),[screenFilter,setScreenFilter]=useState<ScreeningFilter>("all"),[selected,setSelected]=useState(""),[view,setView]=useState("分类看板");
  useEffect(()=>{ if(new URLSearchParams(window.location.search).get("cards")==="1")setView("红利筛选摘要"); },[]);
  const [page,setPage]=useState(1),[search,setSearch]=useState("");
  const debouncedSearch=useDebouncedValue(search);
  useEffect(()=>setPage(1),[category,sector,onlyLow,screenFilter,search]);
  const summary=useReadResource<Board>(`${marketApiUrl()}/dividends/summary`,d=>d?.status==="running"?2000:15000);
  const params=new URLSearchParams({page:String(page),query:debouncedSearch,category,sector,only_low:String(onlyLow),screen:screenFilter,selected,...(summary.data?.snapshot_version?{version:summary.data.snapshot_version}:{})});
  const result=useReadResource<Board>(`${marketApiUrl()}/dividends/stocks?${params}`,0);
  useEffect(()=>{if(result.errorStatus===409)summary.refresh();},[result.errorStatus,summary.refresh]);
  const data=result.data?{...result.data,...Object.fromEntries(Object.entries(summary.data||{}).filter(([k])=>["status","progress","checked","scanned","error"].includes(k)))}:null;
  const error=scanError||result.error||summary.error;
  async function scan(){setScanError("");try{const r=await fetch(`${marketApiUrl()}/dividends/scan`,{method:"POST"});const p=await r.json();if(!r.ok)throw new Error(p.detail||"无法启动扫描");summary.refresh();}catch(e){setScanError(String(e));}}
  const baseRows=data?.stocks||[];
  const quotes=useLiveQuotes([...baseRows.map(s=>s.code),...(selected?[selected]:[])]);
  const liveStocks=useMemo(()=> ([...(data?.stocks||[]),...(data?.selected_stock&&!data.stocks.some(s=>s.code===data.selected_stock?.code)?[data.selected_stock]:[])]).map(s=>{
    const quote=quotes.data?.quotes.find(q=>q.code===s.code);
    if(!quote)return s;
    const d=state.companies?.[s.code]?.info?.dividend;
    const cash=d?.verified&&d.cashPerShare!=null&&d.asOf===quote.quote_time.slice(0,10)?d.cashPerShare:s.cashPerShare;
    const min=s.historyLow??(s.history.length?Math.min(...s.history):null),max=s.historyHigh??(s.history.length?Math.max(...s.history):null),lowPosition=min!=null&&max!=null?(max===min?50:Math.max(0,Math.min(100,(quote.price-min)/(max-min)*100))):null,dividendYield=cash/quote.price*100;
    return {...s,cashPerShare:cash,price:quote.price,dividendYield,lowPosition,quoteTime:quote.quote_time,drawdown:max?(quote.price/max-1)*100:null,signal:lowPosition==null?"unknown":lowPosition<=(data?.config?.dividend_low_position_pct??35)?"stage":lowPosition>=(data?.config?.dividend_high_position_pct??70)?"wait":"watch"};
  }),[data,quotes.data,state.companies]);
  const categories=data?.categories||[];
  const industries=data?.industries||[];
  const hasScreening=(data?.strategyVersion??0)>=3;
  const passingCount=data?.passing_count??0;
  const matchedCount=data?.matched??0;
  const showAllMatches=hasScreening&&screenFilter==="pass";
  const pageCount=Math.max(1,Math.ceil(matchedCount/50));
  const pageRows=liveStocks.filter(s=>baseRows.some(r=>r.code===s.code));
  const ranked=pageRows;
  useEffect(()=>{if(!result.loading&&page>pageCount)setPage(pageCount);},[page,pageCount,result.loading]);
  const chosen=liveStocks.find(s=>s.code===selected)||pageRows[0];
  const chosenCompany=chosen?state.companies?.[chosen.code]:undefined;
  useCompanyProfiles(chosenCompany?[chosenCompany.code]:[],setState);
  useEffect(()=>{if(!chosen?.code)return;let active=true;fetchCompanyInfo(chosen.code).then(info=>{if(active)setState(s=>upsertCompany(s,info,"view","红利看板"));}).catch(e=>{if(active)setActionError(String(e));});return()=>{active=false;};},[chosen?.code,setState]);
  const avg=data?.average_yield;
  function exportPNG(){
    if(!ranked.length)return;
    const canvas=document.createElement("canvas");canvas.width=1080;canvas.height=360+pageRows.length*118;const c=canvas.getContext("2d");if(!c)return;
    c.fillStyle="#fffdfb";c.fillRect(0,0,1080,1440);c.fillStyle="#913045";c.fillRect(0,0,1080,250);c.fillStyle="white";c.font="32px sans-serif";c.fillText("攒股躺平日记 · 真实数据",60,75);c.font="bold 54px sans-serif";c.fillText("高股息观察看板",60,150);c.font="26px sans-serif";c.fillText(`${data?.tradeDate} · ${category} · 分类规则排序`,60,210);
    pageRows.forEach((s,i)=>{const y=320+i*118;c.fillStyle=i%2?"#f7f1ed":"#fffdfb";c.fillRect(40,y-45,1000,108);c.fillStyle="#242323";c.font="bold 30px sans-serif";c.fillText(`${i+1}. ${s.name}`,65,y);c.font="21px sans-serif";c.fillStyle="#746f6b";c.fillText(`${s.code} · ${s.sector}`,65,y+35);c.fillStyle="#913045";c.font="bold 29px sans-serif";c.fillText(`${fixed(s.dividendYield,2)}%`,590,y);c.fillText(`位置${fixed(s.lowPosition,0)}%`,810,y);});
    c.fillStyle="#746f6b";c.font="23px sans-serif";c.fillText("已实施税前现金分红；财务分层用于候选研究。",60,canvas.height-80);c.fillText("各标的报价时间以看板为准，发布前复核公司公告。",60,canvas.height-40);
    const a=document.createElement("a");a.download=`红利观察-${data?.tradeDate}-${category}.png`;a.href=canvas.toDataURL("image/png");a.click();
  }
  return <div className="space-y-5"><Card className="!bg-[#692131] !text-white"><div className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-xs tracking-widest text-rose-100/70">攒股躺平日记 · 红利研究</p><h2 className="mt-2 text-2xl font-semibold">高股息观察看板</h2><p className="mt-2 text-sm text-rose-100/70">先核对历史派息和财务覆盖，再看价格位置与公告证据。</p></div><span className="rounded-full border border-white/20 px-3 py-2 text-xs">真实全A股扫描 · 无演示回退</span></div></Card>
    <Card><div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="font-semibold">{data?.progress||"正在连接扫描服务…"}</h3><p className="mt-1 text-xs text-slate-400">{data?.updatedAt?`上次完整扫描：${new Date(data.updatedAt).toLocaleString("zh-CN")} · 行情日 ${data.tradeDate}`:"首次请启动全市场扫描，扫描期间可查看进度。"}</p></div><button className={buttonClass} disabled={data?.status==="running"} onClick={scan}>{data?.status==="running"?"正在扫描…":"扫描 / 更新真实数据"}</button></div>{error&&<p className="mt-3 text-sm text-red-700">{error}</p>}{data?.status==="error"&&<p className="mt-3 text-sm text-red-700">本次扫描失败。下方若有数据，仍是上次成功扫描，不能视作已更新。</p>}<div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4"><Metric label="全A股覆盖" value={String(data?.scanned||0)}/><Metric label="量化通过" value={String(data?.preselected||0)}/><Metric label="日线核验" value={String(data?.checked||0)}/><Metric label="匹配数量 / 扫描平均息率" value={`${matchedCount} / ${avg==null?"未知":avg.toFixed(2)+"%"}`}/></div></Card>
    <Card><div className="grid gap-3 sm:grid-cols-4"><Field label="代码或名称"><input className={inputClass} value={search} onChange={e=>setSearch(e.target.value)} placeholder="搜索完整A股母池"/></Field><Field label="行业大类"><select className={inputClass} value={category} onChange={e=>{setCategory(e.target.value);setSector("全部");}}><option>全部</option>{categories.map(c=><option key={c}>{c}</option>)}</select></Field><Field label="细分行业"><select className={inputClass} value={sector} onChange={e=>setSector(e.target.value)}><option>全部</option>{industries.map(s=><option key={s}>{s}</option>)}</select></Field><Field label="展示方式"><select className={inputClass} value={view} onChange={e=>setView(e.target.value)}><option>分类看板</option><option>红利筛选摘要</option></select></Field><div className="flex items-end gap-3"><label className="text-sm"><input type="checkbox" checked={onlyLow} onChange={e=>setOnlyLow(e.target.checked)}/> 仅低位观察</label><button className={secondaryButtonClass} disabled={!ranked.length||result.loading||search!==debouncedSearch} onClick={exportPNG}>导出当前页PNG</button></div></div><p className="mt-3 text-xs text-slate-400">列表为标注日期的扫描筛选快照，点击公司后查看统一实时资料与K线。分类排名基于上次完整扫描评分。筛选、统计与翻页固定为同一完整扫描版本；当前页报价单独刷新，不改变快照筛选归属。所有股票均可查询。其他页保留各自扫描时间，不混称全部实时。</p>{result.loading&&<p role="status" className="mt-2 text-xs text-slate-500">正在查询完整母池，暂保留上一页结果…</p>}{quotes.error&&<p className="mt-2 text-xs text-amber-700">报价刷新失败：{quotes.error}，保留已标注时间的扫描快照。</p>}</Card>
    <Card><div className="flex flex-wrap items-center gap-3 text-sm"><button className={secondaryButtonClass} disabled={page<=1} onClick={()=>{setPage(p=>p-1);setSelected("");}}>上一页</button><span>第{page}/{pageCount}页 · 匹配{matchedCount}只 · 每页50只 · 后台扫描不截断</span><button className={secondaryButtonClass} disabled={page>=pageCount} onClick={()=>{setPage(p=>p+1);setSelected("");}}>下一页</button></div></Card>
    {data?.stocks.length && !data.strategyVersion ? <Card>当前展示的是旧策略快照。重新扫描后，分类列表会按新版财务证据排序。</Card> : null}
    {hasScreening && <Card>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h3 className="font-semibold">六维框架 · 自动筛选</h3><p className="mt-1 text-sm text-slate-600">量化通过 {passingCount} / {data?.total??0} 只 · 以扫描日数据判定</p></div>
        <Field label="筛选结果"><select className={inputClass} value={screenFilter} onChange={event=>setScreenFilter(event.target.value as ScreeningFilter)}>
          <option value="pass">仅显示量化通过</option><option value="all">全部已核验候选</option><option value="supported">仅看财务证据支持</option>
          <option value="fail">未达标</option><option value="unknown">数据不足</option><option value="manual">需人工复核</option>
        </select></Field>
      </div>
      <p className="mt-2 text-xs leading-6 text-slate-500">仅显示量化通过时，不限制每类展示数量。历史估值、行业与治理仍需核对。</p>
    </Card>}
    <Card><details className="text-sm leading-7 text-slate-700">
      <summary className="cursor-pointer font-semibold text-slate-950">六维框架与参考区间</summary>
      <p className="mt-2">参考《衡量红利股投资价值的评估框架》。先看盈利、派息与现金覆盖，再看估值、行业与利率。原框架所用的股息率约3%–6%、连续派息至少5年、支付率约30%–70%、经营现金流覆盖约1.5倍、经营现金流与净利约0.8倍，均为研究参考。支付率和现金流口径需按行业及资本需求调整。</p>
      <p>查看个股的「展开六维评估」。自动筛选采用框架中的4%–6%区间和至少2个百分点的股债差，并检查自由现金流覆盖及既有财务风险分层。逐项门槛可展开查看。</p>
    </details></Card>
    {!ranked.length&&<Card>{hasScreening ? "当前筛选下没有候选。可切换筛选结果，查看未通过或待复核的原因。" : "尚无可用筛选结果。请扫描真实数据。"}</Card>}
    {ranked.length>0&&view==="分类看板"&&<div className="grid items-start gap-5 xl:grid-cols-[1.6fr_1fr]"><Card><h3 className="text-lg font-semibold">{showAllMatches ? "量化通过 · 全部匹配" : "全A股分类结果 · 无数量截断"}</h3><div className="mt-4 overflow-x-auto"><table className="w-full min-w-[720px] text-left text-sm"><thead className="border-b text-xs text-slate-400"><tr>{["公司","分类/行业","财务核验","连续派息","近12月息率","现价","价格位置","状态"].map(v=><th className="py-3" key={v}>{v}</th>)}</tr></thead><tbody>{pageRows.map(s=><tr key={s.code} onClick={()=>setSelected(s.code)} className="cursor-pointer border-b border-slate-100 hover:bg-rose-50"><td className="py-3"><button className="text-left" onClick={()=>setSelected(s.code)}><strong>{s.name}</strong><small className="block text-slate-400">{s.code}</small></button></td><td className="text-xs">{s.category}<br/>{s.sector}</td><td className="text-xs">{s.quality ? qualityLabels[s.quality.status] : "旧策略"}{s.screening && <span className="block text-slate-500">{screeningLabels[s.screening.status]}</span>}</td><td>{s.consecutiveYears}年</td><td className="font-semibold text-[#913045]">{fixed(s.dividendYield,2)}%</td><td>{fixed(s.price,2)}</td><td>{fixed(s.lowPosition,0)}%</td><td className="text-xs">{signalName(s.signal)}</td></tr>)}</tbody></table></div></Card>{chosen&&<Card><h3 className="text-xl font-semibold">{chosen.name} <span className="text-sm font-normal text-slate-400">{chosen.code}</span></h3><p className="mt-2 text-xs text-slate-400">报价时间 {(chosen.quoteTime?new Date(chosen.quoteTime).toLocaleString("zh-CN"):"未知")}</p><div className="mt-4 flex flex-wrap gap-2"><button disabled={joining} className={buttonClass} onClick={()=>state.companies?.[chosen.code]?.inWatchlist?navigateInvestmentView("watchlist",chosen.code):join(chosen.code)}>{state.companies?.[chosen.code]?.inWatchlist?"查看观察池":"加入观察池"}</button><button disabled={joining} className={secondaryButtonClass} onClick={()=>join(chosen.code,true)}>{state.companies?.[chosen.code]?.inWatchlist?"打开研究":"加入并研究"}</button></div><QualityDetails quality={chosen.quality}/><ScreeningDetails screening={chosen.screening}/><FrameworkDetails stock={chosen} benchmark={data?.benchmark}/>{chosenCompany&&<div className="mt-4"><CompanyFacts company={chosenCompany}/></div>}<div className="mt-5"><CompanyKline code={chosen.code}/></div><p className="mt-3 text-xs text-slate-400">下面为扫描时保存的分红记录；当前公司资料、研究区间及失效条件使用统一公司档案。</p><h4 className="mt-5 font-medium">已实施分红记录</h4>{chosen.dividendRecords.slice(0,6).map((r,i)=><div key={i} className="flex justify-between border-b py-2 text-xs"><span>{r.exDate}</span><span>每股 ¥{r.cashPerShare.toFixed(3)}</span></div>)}</Card>}</div>}
    {view==="红利筛选摘要"&&ranked.length>0&&<div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{pageRows.map(s=><Card key={s.code}><p className="text-xs text-[#913045]">{s.category} · {s.sector}</p><h3 className="mt-2 text-xl font-semibold">{s.name}</h3><p className="mt-3 text-3xl font-semibold text-[#913045]">{fixed(s.dividendYield,2)}%</p><p className="mt-2 text-sm text-slate-500">窗口内连续派息 {s.consecutiveYears} 年 · 价格位置 {fixed(s.lowPosition,0)}%</p><p className="mt-3 text-sm">规则状态：{signalName(s.signal)}</p><div className="mt-4 flex flex-wrap gap-2"><button disabled={joining} className={secondaryButtonClass} onClick={()=>state.companies?.[s.code]?.inWatchlist?navigateInvestmentView("watchlist",s.code):join(s.code)}>{state.companies?.[s.code]?.inWatchlist?"查看观察池":"加入观察池"}</button><button disabled={joining} className={secondaryButtonClass} onClick={()=>{setSelected(s.code);setView("分类看板");}}>查看公司与K线</button></div><QualityDetails quality={s.quality}/><ScreeningDetails screening={s.screening}/><FrameworkDetails stock={s} benchmark={data?.benchmark}/><p className="mt-3 text-xs leading-6 text-slate-500">治理线索：在公司公告核对实际控制人、第一大股东持股和分红政策。股权性质不参与排名。</p><p className="mt-3 text-xs text-slate-400">{(s.quoteTime?new Date(s.quoteTime).toLocaleString("zh-CN"):"未知")}</p></Card>)}</div>}
    {actionError&&<Card><p role="alert" className="text-sm text-red-700">公司资料读取失败：{actionError}</p><p className="mt-2 text-xs text-slate-400">未创建空白或重复档案，请稍后重试。</p></Card>}<Card><h3 className="font-semibold">口径与异常</h3>{data?.notes?.map(n=><p className="mt-2 text-xs leading-6 text-slate-500" key={n}>{n}</p>)}{data?.failure_count?<DividendFailures count={data.failure_count} version={data.snapshot_version}/>:null}<p className="mt-3 text-xs text-slate-400">从另一份quant-copilot迁入分类规则与红利筛选摘要流程。高股息不等于低风险；数据以公司公告复核，不构成投资建议。</p></Card>
  </div>;
}


function DividendFailures({count,version}:{count:number;version?:string}){
 const [open,setOpen]=useState(false),[page,setPage]=useState(1);
 const params=new URLSearchParams({page:String(page),...(version?{version}:{})});
 const result=useReadResource<{rows:string[];total:number}>(open?`${marketApiUrl()}/dividends/failures?${params}`:null,0);
 return <details className="mt-3 text-xs text-amber-700" onToggle={e=>setOpen(e.currentTarget.open)}><summary>查看{count}项排除 / 数据异常</summary>{open&&<><div className="mt-2 max-h-52 overflow-auto">{result.data?.rows.map((f,i)=><p className="py-1" key={i}>{f}</p>)}</div>{result.error&&<p>{result.error}</p>}<div className="mt-2 flex gap-3"><button disabled={page<=1} onClick={()=>setPage(v=>v-1)}>上一页异常</button><span>{page}/{Math.max(1,Math.ceil(count/50))}</span><button disabled={page>=Math.ceil(count/50)} onClick={()=>setPage(v=>v+1)}>下一页异常</button></div></>}</details>;
}
