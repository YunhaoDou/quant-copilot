"use client";
import { useEffect, useState } from "react";
import {useReadResource,useDebouncedValue} from "@/lib/read-resource";
import { marketApiUrl } from "@/lib/live-market";
import { accountRulesSuffix, accountStatusText, formatAccountTime, toAccountView, type TradeView } from "@/lib/account-view";
import { Card, buttonClass, secondaryButtonClass, money } from "./ui";
import PaperAccountCard from "./PaperAccountCard";
import TradeTable from "./TradeTable";
import ShiborSimulationPanel from "./ShiborSimulationPanel";
import TrendLeaderPanel from "./TrendLeaderPanel";
import CycleStrategySimulation from "./CycleStrategySimulation";
import LegacySimSection from "./LegacySimSection";

type Account = {
  status: string; capital: number; cash: number; equity: number; peak: number; created_at: string;
  position: { symbol: string; name: string; quantity: number; mark: number; mark_time: string } | null;
  pending: { symbol: string; side: string; reason: string } | null;
  candidates?: { code: string; name: string; quote_time: string | null; status: string; checks: { label: string; passed: boolean | null; value?: number | null; minimum?: number | null; maximum?: number | null }[] }[];
  data?: { generated_at: string; financial_date: string; pool_total: number; checked: number; failures: string[] };
  rules: Record<string, number>;
  decisions: { time: string; text: string }[];
  trades: { time: string; symbol: string; side: string; price: number; quantity: number; pnl: number | null; reason: string; universe_scope?:string }[];
};
type Strategy = { id: string; name: string; logic: string; evidence: string; entry: string; exit: string; source?: string; account: Account | null };
type Payload = { experiment?: {start_date:string;review_date:string;changed_at:string;notes:string[]}; market_scan?: {total:number;state:string;evidence_state:string;error:string|null}; strategies: Strategy[]; refresh: { state: string; error: string | null; updated_at: string | null;total?:number;checked?:number;valid?:number;failed?:number }; universe: string };
const url = "/invest?view=trade&tab=strategies";
const time = formatAccountTime;
const status = (value: string) => ({ pass: "条件满足", fail: "条件未满足", unknown: "数据不足" }[value] || value);

export default function StrategyCenterPanel({ strategyId }: { strategyId: string | null }) {
  const overview=useReadResource<Payload>(`${marketApiUrl()}/strategy-center/overview${strategyId?`?detail_id=${encodeURIComponent(strategyId)}`:""}`,30000);
  const data=overview.data;
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState("all");
  const [candidatePage,setCandidatePage]=useState(1),[candidateQuery,setCandidateQuery]=useState("");
  const debouncedQuery=useDebouncedValue(candidateQuery);
  useEffect(()=>setCandidatePage(1),[filter,candidateQuery,strategyId]);
  const params=new URLSearchParams({page:String(candidatePage),status:filter,query:debouncedQuery});
  const ordinary=strategyId&&!['leader-rebound','trend-leader-band','shibor-rotation'].includes(strategyId);
  const candidates=useReadResource<{rows:NonNullable<Account["candidates"]>;total:number}>(ordinary?`${marketApiUrl()}/strategy-center/${strategyId}/candidates?${params}`:null,30000);
  const candidateData=candidates.data;
  async function act(path:string){
    setBusy(true);
    try{
      const response=await fetch(`${marketApiUrl()}/strategy-center${path}`,{method:"POST"});
      const payload=await response.json();if(!response.ok)throw new Error(payload.detail||"策略操作失败");
      setError("");overview.refresh();candidates.refresh();
    }catch(e){setError(String(e));}finally{setBusy(false);}
  }
  const selected = data?.strategies.find(row => row.id === strategyId);
  const account = selected?.account;
  const accountView = toAccountView(account);
  const trades: TradeView[] | undefined = account?.trades?.map((row) => ({
    time: time(row.time), symbol: row.symbol, side: row.side, price: row.price,
    quantity: row.quantity, pnl: row.pnl, reason: row.reason, note: row.universe_scope,
  }));
  return <div className="space-y-5">
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-4"><div>
        <h2 className="text-2xl font-semibold">策略研究与独立模拟</h2>
        <p className="mt-2 max-w-3xl text-sm leading-7 text-slate-600">每个策略各用10万元虚拟资金，收益和持仓分别记录。研究方向具有不同程度的历史证据，页面中的具体规则仍需用样本外结果检验。</p>
      </div><div className="flex flex-wrap gap-2">
        <button disabled={busy} className={buttonClass} onClick={() => act("/start-all")}>启动全部独立模拟</button>
        <button disabled={busy} className={secondaryButtonClass} onClick={() => act("/refresh")}>更新候选与日线</button>
      </div></div>
      {data?.experiment && <div className="mt-4 rounded-xl bg-emerald-50 p-4 text-sm leading-7 text-emerald-950"><p className="font-semibold">原七策略观察期：{data.experiment.start_date} 起 · {data.experiment.review_date} 复核</p><p>全A股股票策略与全ETF追踪分别保留；新增SHIBOR模拟按实际启动日独立计时。</p><p className="text-xs">切换前缺少完整全A股采集，已有交易按原范围标记；不补造昨天的交易或信号。</p></div>}
      <p className="mt-3 text-xs leading-6 text-slate-500">{data?.universe} · {data?.refresh.state || "正在读取"}{data?.refresh.error && ` · ${data.refresh.error}`}</p>
      <p className="mt-1 text-xs leading-6 text-slate-500">完整母池 {data?.market_scan?.total ?? 0} 只 · {data?.market_scan?.evidence_state || data?.market_scan?.state} · 日线核验 {data?.refresh.checked ?? 0}/{data?.refresh.total ?? 0} · 日线可用 {data?.refresh.valid ?? "待汇总"} · 不足或失败 {data?.refresh.failed ?? "待汇总"}。完整核验结果已保存，按页展示并可查询所有代码；扫描范围不截断。{data?.market_scan?.error}</p>
      <p className="mt-1 text-xs leading-6 text-slate-500">日线信号使用当前日期以前的已完成交易日，价格和估值来自公开报价。后端在盘中核验并按后续报价撮合，休市时只更新候选观察。T+1、涨跌停等待、整手、费用和滑点沿用影子账户规则，尚未模拟盘口排队与成交量容量。</p>
      <p className="mt-1 text-xs leading-6 text-slate-500">同一轮多个标的满足时，质量价值优先较低PE，红利现金流优先较高历史中位股息率，红利低波优先较低波动，基本面趋势优先较高年报利润增速，相对强势优先较高超额。前五个股票账户同时持有一只股票；SHIBOR的双ETF配置、月频执行及风险防线见独立页面。</p>
      {(error||overview.error||candidates.error) && <p role="alert" className="mt-3 text-sm text-red-700">{error||overview.error||candidates.error}</p>}
    </Card>
    {!selected && <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {data?.strategies.map(spec => <Card key={spec.id}>
        <h3 className="text-lg font-semibold">{spec.name}</h3><p className="mt-2 text-sm leading-7 text-slate-600">{spec.logic}</p>
        <p className="mt-3 text-xs leading-6 text-slate-500">{spec.evidence}</p>
        {spec.account && <p className="mt-3 text-sm">{spec.account.status === "running" ? "运行中" : "已暂停"} · 参考权益 {money(spec.account.equity)}</p>}
        <a className={`${secondaryButtonClass} mt-4 inline-flex`} href={`${url}&strategy=${spec.id}`}>打开{spec.name}</a>
      </Card>)}
    </div>}
    {selected && <>
      <nav aria-label="策略页面" className="flex flex-wrap gap-2"><a href={url} className={secondaryButtonClass}>返回策略目录</a>
        {data?.strategies.map(spec => <a className={`${secondaryButtonClass} aria-[current=page]:bg-emerald-50`} aria-current={spec.id === selected.id ? "page" : undefined} href={`${url}&strategy=${spec.id}`} key={spec.id}>{spec.name}</a>)}
      </nav>
      <Card><h3 className="text-xl font-semibold">{selected.name}</h3>
        <dl className="mt-3 space-y-3 text-sm leading-7 text-slate-700">{[["逻辑", selected.logic], ["证据与边界", selected.evidence], ["入场", selected.entry], ["退出", selected.exit]].map(([label,text]) => <div key={label}><dt className="font-semibold">{label}</dt><dd>{text}</dd></div>)}</dl>
        {selected.source && <a href={selected.source} target="_blank" rel="noreferrer" className="mt-3 inline-block text-xs text-emerald-800 underline">原始研究或规则资料</a>}
      </Card>
      {selected.id === "shibor-rotation" ? <ShiborSimulationPanel /> : selected.id === "trend-leader-band" ? <TrendLeaderPanel /> : selected.id === "leader-rebound" ? <CycleStrategySimulation /> : <>
        <PaperAccountCard
          title={`独立账户 · ${accountStatusText(accountView)}`}
          account={accountView}
          busy={busy}
          actions={[
            { id: "start", label: "继续模拟", onClick: () => act(`/${selected.id}/start`) },
            { id: "pause", label: "暂停模拟", onClick: () => act(`/${selected.id}/pause`) },
            { id: "exit", label: "请求模拟退出", onClick: () => act(`/${selected.id}/exit`) },
          ]}
          meta={account && <p className="mt-3 text-xs leading-6 text-slate-500">创建 {time(account.created_at)}{accountRulesSuffix(account.rules)}</p>}
          position={account && <p className="mt-2 text-sm">{account.position ? `${account.position.name} ${account.position.symbol} · ${account.position.quantity}股 · 最近估值价${account.position.mark.toFixed(3)} · ${time(account.position.mark_time)}` : "当前无模拟持仓"}</p>}
          pending={account?.pending && <p className="mt-2 text-sm text-amber-800">待处理 {account.pending.symbol} · {account.pending.side === "buy" ? "模拟买单" : "模拟卖单"} · {account.pending.reason}</p>}
        />
        <Card><h4 className="font-semibold">逐项候选核验</h4>
          {account?.data && <p className="mt-2 text-xs leading-6 text-slate-500">财务快照 {account.data.financial_date} · 本轮日线核验 {account.data.checked}/{account.data.pool_total} 只 · 生成 {time(account.data.generated_at)} · 失败 {account.data.failures.length} 项</p>}
          <label className="mt-3 block text-sm">显示候选<select className="ml-2 rounded-lg border p-2" value={filter} onChange={e => setFilter(e.target.value)}><option value="pass">条件满足</option><option value="all">全部</option><option value="fail">条件未满足</option><option value="unknown">数据不足</option></select></label>
          <label className="mt-3 block text-sm">查询全A股核验<input aria-label="查询全A股核验" className="ml-2 rounded-lg border p-2" value={candidateQuery} onChange={e=>setCandidateQuery(e.target.value)} placeholder="代码或名称"/></label>
          <div className="mt-3 space-y-3">{candidateData?.rows.map(row => <details className="border-t pt-3 text-sm" key={row.code}>
            <summary className="cursor-pointer font-medium">{row.name} {row.code} · {status(row.status)}</summary>
            <p className="mt-2 text-xs text-slate-500">报价 {row.quote_time?time(row.quote_time):"缺失"}</p>
            <ul className="mt-2 space-y-1 text-xs leading-6">{row.checks.map(item => <li key={item.label} className={item.passed ? "text-emerald-800" : "text-slate-600"}>{item.label} · {item.value == null ? "" : Number(item.value.toFixed(2))} · {item.passed === null ? "未知" : item.passed ? "满足" : "未满足"}{item.minimum != null && ` · 下限 ${item.minimum}`}{item.maximum != null && ` · 上限 ${item.maximum}`}</li>)}</ul>
          </details>)}</div>
          <div className="mt-4 flex flex-wrap items-center gap-3 text-sm"><button className={secondaryButtonClass} disabled={candidatePage<=1} onClick={()=>setCandidatePage(p=>p-1)}>上一页</button><span>第{candidatePage}/{Math.max(1,Math.ceil((candidateData?.total||0)/50))}页 · 匹配{candidateData?.total??0}只；全母池结果可查询</span><button className={secondaryButtonClass} disabled={candidatePage>=Math.ceil((candidateData?.total||0)/50)} onClick={()=>setCandidatePage(p=>p+1)}>下一页</button></div>
          {!candidateData?.rows.length && <p className="mt-3 text-sm text-slate-500">当前没有此类候选。可切换全部查看，或等待数据核验。</p>}
        </Card>
        <Card><h4 className="font-semibold">判断日志</h4><div className="mt-3 max-h-80 overflow-auto">{account?.decisions?.slice().reverse().map((row,i) => <div key={i} className="border-t py-3 text-sm leading-7"><p className="text-xs text-slate-500">{time(row.time)}</p><p>{row.text}</p></div>)}</div></Card>
        <Card><h4 className="font-semibold">模拟成交流水</h4>
          <TradeTable rows={trades} />
        </Card>
      </>}
    </>}
    <LegacySimSection />
  </div>;
}
