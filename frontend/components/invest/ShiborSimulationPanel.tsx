"use client";
import {useState} from "react";
import {LineChart,Line,XAxis,YAxis,Tooltip,ResponsiveContainer,CartesianGrid} from "recharts";
import {useVisiblePoll} from "@/lib/read-resource";
import {marketApiUrl} from "@/lib/live-market";
import {accountStatusLabel, formatAccountTime, toAccountView, type TradeView} from "@/lib/account-view";
import {Card,Metric,money} from "./ui";
import PaperAccountCard from "./PaperAccountCard";
import TradeTable, {tradeColumn} from "./TradeTable";
type Account={status:string;created_at:string;review_date:string;capital:number;cash:number;equity:number;peak:number;fees:number;positions:Record<string,{symbol:string;name:string;quantity:number;cost_price:number;mark:number;mark_time:string}>;pending:{kind:string;reason:string}|null;signal:{as_of:string;rate:number;smooth_rate:number;percentile:number;reason:string}|null;rules:{history_quotes:number;smoothing_quotes:number;low_percentile:number;cost_bps:number;slippage_bps:number;min_commission:number;drawdown_pause_pct:number};trades:{time:string;symbol:string;name:string;side:string;quantity:number;price:number;fee:number;reason:string}[];decisions:{time:string;text:string}[];curve:{date:string;equity:number}[]};
type Data={account:Account|null;runtime:{state:string;error:string|null;updated_at:string};feed:{source?:string;last_date?:string;observed_at?:string};note:string};
const time=formatAccountTime;
export default function ShiborSimulationPanel(){
 const [data,setData]=useState<Data|null>(null),[error,setError]=useState(""),[busy,setBusy]=useState(false);
 useVisiblePoll(async signal=>{try{const r=await fetch(`${marketApiUrl()}/shibor-sim`,{signal,cache:"no-store"});if(!r.ok)throw new Error("读取模拟账户失败");setData(await r.json());setError("");}catch(e){if(!signal.aborted)setError(String(e));}},10000);
 async function action(name:string){setBusy(true);try{const r=await fetch(`${marketApiUrl()}/shibor-sim/${name}`,{method:"POST"});const d=await r.json();if(!r.ok)throw new Error(d.detail||"模拟操作失败");setData(d);setError("");}catch(e){setError(String(e));}finally{setBusy(false);}}
 const a=data?.account,s=a?.signal,accountView=toAccountView(a);
 const trades:TradeView[]|undefined=a?.trades.slice().reverse().map(t=>({time:time(t.time),symbol:t.symbol,side:t.side,price:t.price,quantity:t.quantity,fee:t.fee,reason:t.reason}));
 return <div className="space-y-5">
  <PaperAccountCard
    title="SHIBOR轮动 · 前向模拟账户"
    headingLevel={3}
    description="独立10万元虚拟资金；512890红利低波 / 159915创业板。与原七个股票策略分别记录。"
    statusLine={<>账户：{accountStatusLabel(a?.status)} · 后台：{data?.runtime.state||"读取中"}</>}
    error={error||data?.runtime.error||null}
    account={accountView}
    busy={busy}
    actions={[{id:"start",label:"继续模拟",onClick:()=>action("start")},{id:"pause",label:"暂停模拟",onClick:()=>action("pause")},{id:"exit",label:"请求模拟退出",onClick:()=>action("exit")}]}
    meta={a&&<>
      <p className="mt-3 text-xs leading-6 text-slate-500">实际启动 {time(a.created_at)} · 独立复核日 {a.review_date} · 已计费用 {money(a.fees)} · 不使用原七策略的起始日补算收益。</p>
      <p className="mt-2 text-xs leading-6 text-amber-800">前向账户增加{a.rules.drawdown_pause_pct}%回撤触发退出与暂停，且计整手、最低佣金与滑点，规则不同于此前无该防线的历史研究；极端行情可能越过防线。</p>
    </>}
  />
  <Card><h3 className="font-semibold">规则与当前决策</h3><p className="mt-3 text-sm leading-7">初始各半。隔夜SHIBOR的{a?.rules.smoothing_quotes??5}日均值处于过去{a?.rules.history_quotes??756}个报价日最低{((a?.rules.low_percentile??.25)*100).toFixed(0)}%时，下月偏向成长，否则偏向红利；月末冻结信号，在次月首个股票交易日收盘模拟执行。错过该收盘不补单。</p><p className="mt-2 text-sm">{a?.pending?`待处理：${a.pending.reason}`:"当前没有待处理订单"}</p>{s?<div className="mt-3 grid gap-3 sm:grid-cols-3"><Metric label={`月末信号 ${s.as_of}`} value={`${s.rate.toFixed(4)}%`}/><Metric label="5日报价均值" value={`${s.smooth_rate.toFixed(4)}%`}/><Metric label="历史分位" value={`${(s.percentile*100).toFixed(2)}%`}/><p className="text-sm sm:col-span-3">{s.reason}</p></div>:<p className="mt-3 text-sm text-slate-500">初始配置不使用过去信号回填，首次月度信号等待下一个月末。</p>}<p className="mt-3 text-xs leading-6 text-slate-500">{data?.feed.source||"SHIBOR源等待采集"} · 最新报价日 {data?.feed.last_date||"未知"} · 采集 {time(data?.feed.observed_at)}</p><p className="mt-2 text-xs leading-6 text-slate-500">费用 {a?.rules.cost_bps??10}基点/单边、最低{a?.rules.min_commission??5}元；滑点 {a?.rules.slippage_bps??5}基点；100份整手、T+1、涨跌停保守不成交。分红依披露入账，未识别拆分暂停核实。</p></Card>
  <Card><h3 className="font-semibold">ETF模拟持仓</h3><div className="mt-3 overflow-x-auto"><table className="w-full min-w-[650px] text-left text-sm"><thead><tr>{["ETF","份额","含费成本","参考价格","报价时间"].map(v=><th key={v} className="py-2">{v}</th>)}</tr></thead><tbody>{Object.values(a?.positions||{}).map(p=><tr className="border-t" key={p.symbol}><td className="py-3">{p.name} {p.symbol}</td><td>{p.quantity}</td><td>{p.cost_price.toFixed(3)}</td><td>{p.mark.toFixed(3)}</td><td>{time(p.mark_time)}</td></tr>)}</tbody></table></div>{!Object.keys(a?.positions||{}).length&&<p className="mt-3 text-sm text-slate-500">当前空仓，等待有效数据及启动之后的可成交报价。</p>}</Card>
  <Card><h3 className="font-semibold">前向权益 · 不拼接历史回测</h3>{a?.curve.length?<div className="mt-4 h-64"><ResponsiveContainer width="100%" height="100%"><LineChart data={a.curve}><CartesianGrid strokeDasharray="3 3"/><XAxis dataKey="date"/><YAxis domain={["auto","auto"]}/><Tooltip/><Line dataKey="equity" name="虚拟权益" stroke="#147957" dot={a.curve.length===1}/></LineChart></ResponsiveContainer></div>:<p className="mt-3 text-sm text-slate-500">等待第一条实际前向记录。</p>}</Card>
  <Card><h3 className="font-semibold">模拟成交流水</h3>
    <TradeTable
      rows={trades}
      minWidthClass="min-w-[900px]"
      emptyText="尚无模拟成交。"
      columns={[tradeColumn("time","供应商报价时间"),tradeColumn("symbol","ETF"),tradeColumn("side"),tradeColumn("quantity","份额"),tradeColumn("price","含滑点价格"),tradeColumn("fee"),tradeColumn("reason","理由")]}
    />
  </Card>
  <Card><h3 className="font-semibold">判断日志</h3><div className="mt-3 max-h-80 overflow-auto">{a?.decisions.slice().reverse().map((d,i)=><p key={i} className="border-t py-3 text-sm leading-7"><span className="block text-xs text-slate-400">{time(d.time)}</span>{d.text}</p>)}</div><p className="mt-3 text-xs leading-6 text-slate-500">{data?.note}</p></Card>
 </div>;
}
