"use client";

import { useEffect, useRef, useState } from "react";
import { marketApiUrl } from "@/lib/live-market";
import { Card, Field, inputClass, buttonClass, secondaryButtonClass } from "./ui";

type Leader = { symbol: string; name: string; boards: number; pct: number | null; first_limit_time: string | null; last_limit_time?: string | null; breaks: number | null };
type Evidence = {
  sector: { code: string; name: string; pct: number | null; limit_up: number | null; started: boolean; checks: Record<string, boolean | null> };
  market: { market_pct: number | null; limit_down: number | null; break_rate: number | null; new_low: boolean | null; risk: string };
  leaders: Leader[] | null; broken: Leader[] | null; quote_time: string; leader_scope: string;
  watched?: { symbol: string; name: string; quote: { price: number; pct: number | null; quote_time: string } | null }[];
};
type EventSummary = {
  id: string; name: string; start_date: string; first_at: string; status: "active" | "closed";
  stage: string; plan: string; invalidation: string; first: Evidence; latest: Evidence; dates: string[];
  evidence: { state: string; pct_change: number | null; limit_up_change: number | null };
};
type EventDetail = EventSummary & {
  history: (Evidence & { observed_at: string })[];
  records: { created_at: string; kind: string; action: string; text: string; symbol?: string; price?: number; quantity?: number }[];
};
const stages = ["待确认", "启动观察", "延续观察", "分歧观察", "回补待确认", "回补确认", "退潮回避", "轮动观察"];
const stageHints: Record<string, string> = {
  待确认: "先复核首次触发、行情日期及市场状态，补齐大盘新低和止跌证据。",
  启动观察: "对照收盘时板块强度、涨停梯队和炸板情况，写出下一次核验条件。",
  延续观察: "比较启动后的持续性、领先股变动与市场风险，核对已有执行计划。",
  分歧观察: "记录板块回落、炸板和领涨股变化，区分实际观察与洗盘假设。",
  回补待确认: "核对板块回升、回封时点及跟风是否同步，等待自己的确认条件。",
  回补确认: "写下确认依据与对应时点，重新核对仓位预算和失效条件。",
  退潮回避: "复核跌停扩散和梯队转弱，按已写下的风险计划处理。",
  轮动观察: "记录多个方向的持续性，检查是否存在可重复的主线证据。",
};
const value = (n: number | null | undefined, suffix = "") => n == null ? "未知" : `${Number(n.toFixed(2))}${suffix}`;
const time = (stamp: string) => new Date(stamp).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" });

async function request(path: string, options?: RequestInit) {
  const response = await fetch(`${marketApiUrl()}/cycle/events${path}`, { cache: "no-store", ...options });
  const payload = await response.json();
  if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : "事件请求失败，请核对输入或稍后重试");
  return payload;
}

export default function CycleEventsPanel({ onResearch }: { onResearch: (code: string) => Promise<void> }) {
  const [events, setEvents] = useState<EventSummary[]>([]);
  const [monitor, setMonitor] = useState<{ state: string; last_success: string | null; error: string | null } | null>(null);
  const [selected, setSelected] = useState("");
  const [detail, setDetail] = useState<EventDetail | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    async function refresh() {
      try {
        const data = await request("", { signal: controller.signal });
        setEvents(data.events);
        setMonitor(data.monitor);
        setSelected(current => current || data.events.find((event: EventSummary) => event.id === new URLSearchParams(window.location.search).get("cycleEvent"))?.id || data.events.find((event: EventSummary) => event.status === "active")?.id || data.events[0]?.id || "");
        setError("");
      } catch (e) { if (!controller.signal.aborted) setError(String(e)); }
    }
    refresh();
    const timer = setInterval(refresh, 30000);
    return () => { controller.abort(); clearInterval(timer); };
  }, [revision]);

  useEffect(() => {
    setDetail(null);
    if (!selected) return;
    const controller = new AbortController();
    async function refresh() {
      try { setDetail(await request(`/${selected}`, { signal: controller.signal })); }
      catch (e) { if (!controller.signal.aborted) setError(String(e)); }
    }
    refresh();
    const timer = setInterval(refresh, 30000);
    return () => { controller.abort(); clearInterval(timer); };
  }, [selected, revision]);

  const now = new Date();
  const today = now.toLocaleDateString("en-CA", { timeZone: "Asia/Shanghai" });
  const clock = now.toLocaleTimeString("en-GB", { timeZone: "Asia/Shanghai", hour12: false });
  const inSession = (clock >= "09:30" && clock <= "11:30") || (clock >= "13:00" && clock <= "15:00");
  const stale = detail && detail.status === "active" && (
    detail.latest.quote_time.slice(0, 10) !== today
    || (inSession && now.getTime() - new Date(detail.latest.quote_time).getTime() > 180000)
  );

  return <div className="space-y-5">
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><h3 className="text-xl font-semibold">板块事件跟踪</h3><p className="mt-2 text-sm leading-7 text-slate-600">首次采集到启动条件后建立事件，持续记录板块、市场和涨停候选。交易日序以已采集日期计数，阶段由你根据证据确认。</p></div>
        <button className={secondaryButtonClass} onClick={() => setRevision(v => v + 1)}>刷新事件</button>
      </div>
      <p className="mt-3 text-xs leading-6 text-slate-500">后台状态 {monitor?.state || "读取中"} · 最近采集 {monitor?.last_success ? time(monitor.last_success) : "尚无"}
        {monitor?.error && ` · ${monitor.error}`}</p>
      <p className="mt-1 text-xs leading-6 text-slate-500">此页只跟踪真实行情，与上方模拟或回放选择独立。后端运行时在工作日盘中窗口采集。休市或断网会出现缺口，恢复后接续。候选来自涨停池及炸板池，行业名称精确匹配，仍需核对实际板块成分。</p>
      {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
    </Card>
    <div className="grid items-start gap-5 xl:grid-cols-[240px_minmax(0,1fr)]">
      <Card><h4 className="font-semibold">事件档案 · {events.length}</h4><div className="mt-3 space-y-2">
        {events.map(event => <button key={event.id} className={`w-full rounded-xl border p-3 text-left text-sm ${selected === event.id ? "border-emerald-400 bg-emerald-50" : "border-slate-200"}`} onClick={() => {
          setSelected(event.id);
          const url = new URL(window.location.href);
          url.searchParams.set("cycleEvent", event.id);
          window.history.replaceState({}, "", url);
        }}>
          <strong>{event.name}</strong><span className="mt-1 block text-xs text-slate-500">{event.start_date} · {event.status === "active" ? "跟踪中" : "已结束"}</span>
          <span className="mt-1 block text-xs">{event.evidence.state}</span>
        </button>)}
        {!events.length && <p className="text-sm leading-7 text-slate-500">等待采集到新的启动事件，或接续当日已有真实快照。</p>}
      </div></Card>
      {detail && detail.id === selected && <div className="min-w-0 space-y-5">
        <Card>
          {stale && <p role="alert" className="mb-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">最新跟踪记录已过期或不是今日行情，请等待后台更新后复核。</p>}
          <h3 className="text-xl font-semibold">{detail.name} · {detail.evidence.state}</h3>
          <p className="mt-2 text-xs leading-6 text-slate-500">首次采集 {time(detail.first_at)} · 最新行情 {time(detail.latest.quote_time)} · 已采集 {detail.dates.length} 个交易日期</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <p className="text-sm">板块涨幅 <strong>{value(detail.latest.sector.pct, "%")}</strong><small className="mt-1 block text-slate-500">较首次变化 {value(detail.evidence.pct_change, " 个百分点")}</small></p>
            <p className="text-sm">板块涨停 <strong>{value(detail.latest.sector.limit_up, " 家")}</strong><small className="mt-1 block text-slate-500">较首次变化 {value(detail.evidence.limit_up_change, " 家")}</small></p>
            <p className="text-sm">大盘涨幅 <strong>{value(detail.latest.market.market_pct, "%")}</strong><small className="mt-1 block text-slate-500">新低确认 {detail.latest.market.new_low === null ? "未知" : detail.latest.market.new_low ? "是" : "否"} · 跌停 {value(detail.latest.market.limit_down)}</small></p>
          </div>
          <div className="mt-3 flex flex-wrap gap-3 text-xs">{Object.entries(detail.latest.sector.checks).map(([key, passed]) => <span key={key} className={passed ? "text-emerald-700" : "text-amber-800"}>{key} · {passed === null ? "未知" : passed ? "满足" : "未满足"}</span>)}</div>
        </Card>
        <Card>
          <h4 className="font-semibold">板块候选梯队</h4>
          <p className="mt-2 text-xs leading-6 text-slate-500">{detail.latest.leader_scope} · 以下是涨停候选的排序结果，失去涨停的股票另在炸板池检查。</p>
          <div className="mt-3 overflow-x-auto"><table className="w-full min-w-[640px] text-left text-xs"><thead><tr>{["股票", "连板", "首封 / 末封", "炸板次数", "操作"].map(label => <th key={label} className="py-2">{label}</th>)}</tr></thead>
            <tbody>{detail.latest.leaders?.map(leader => <tr key={leader.symbol} className="border-t"><td className="py-3">{leader.name}<small className="block text-slate-500">{leader.symbol}</small></td><td>{leader.boards}</td><td>{leader.first_limit_time || "未知"} / {leader.last_limit_time || "未知"}</td><td>{leader.breaks ?? "未知"}</td><td><ResearchButton symbol={leader.symbol} onResearch={onResearch} /></td></tr>)}</tbody>
          </table></div>
          {detail.latest.leaders === null && <p className="mt-2 text-xs text-amber-800">涨停池不可用。</p>}
          <p className="mt-3 text-xs leading-6 text-slate-600">板块炸板候选 {detail.latest.broken === null ? "未知" : detail.latest.broken.map(row => `${row.name}（${row.symbol}）`).join("、") || "当前未匹配到"}。</p>
          <p className="mt-2 text-xs leading-6 text-slate-500">首次候选：{detail.first.leaders?.map(row => `${row.name}（${row.symbol}）`).join("、") || "未知或无匹配"}。候选从当前涨停池消失时，请结合炸板池及个股行情核对其后续状态。</p>
          <h5 className="mt-4 font-semibold">曾入选候选 · 持续报价</h5>
          <div className="mt-2 overflow-x-auto"><table className="w-full min-w-[580px] text-left text-xs">
            <thead><tr>{["股票", "最新价", "涨跌幅", "报价时间"].map(label => <th className="py-2" key={label}>{label}</th>)}</tr></thead>
            <tbody>{detail.latest.watched?.map(row => <tr key={row.symbol} className="border-t"><td className="py-2">{row.name} {row.symbol}</td><td>{value(row.quote?.price, " 元")}</td><td>{value(row.quote?.pct, "%")}</td><td>{row.quote ? time(row.quote.quote_time) : "未知"}</td></tr>)}</tbody>
          </table></div>
        </Card>
        <EventEditor key={detail.id} event={detail} onSaved={data => {
          setDetail(data);
          setEvents(current => current.map(event => event.id === data.id ? data : event));
        }} />
        <Card><h4 className="font-semibold">自动证据时间线</h4><p className="mt-1 text-xs text-slate-500">最近120个采集点；首次快照独立保留。首次记录是系统最早采集时点。</p>
          <div className="mt-3 max-h-80 overflow-auto"><table className="w-full min-w-[580px] text-left text-xs"><thead><tr>{["行情时间", "板块涨幅", "涨停", "候选首位", "市场跌停", "条件"].map(label => <th key={label} className="py-2">{label}</th>)}</tr></thead><tbody>
            {detail.history.map(row => <tr className="border-t" key={row.quote_time}><td className="py-2">{time(row.quote_time)}</td><td>{value(row.sector.pct, "%")}</td><td>{value(row.sector.limit_up)}</td><td>{row.leaders?.[0]?.name || "未知或无匹配"}</td><td>{value(row.market.limit_down)}</td><td>{row.sector.started ? "满足" : "待复核"}</td></tr>)}
          </tbody></table></div>
        </Card>
        <Card><h4 className="font-semibold">判断与执行记录</h4><div className="mt-3 space-y-3">{detail.records.map((record, index) => <div key={index} className="border-t pt-3 text-sm leading-7">
          <p className="text-xs text-slate-500">{time(record.created_at)} · {record.kind} · {record.action}</p>
          {record.symbol && <p>{record.symbol} · {record.price ?? "未填"} 元 · {record.quantity ?? "未填"} 股</p>}
          <p className="whitespace-pre-wrap break-words">{record.text}</p>
        </div>)}</div>{!detail.records.length && <p className="mt-3 text-sm text-slate-500">尚未填写。</p>}</Card>
      </div>}
    </div>
  </div>;
}

function ResearchButton({ symbol, onResearch }: { symbol: string; onResearch: (code: string) => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return <><button className={secondaryButtonClass} disabled={busy} onClick={async () => {
    setBusy(true);
    try { await onResearch(symbol); } catch { setError("公司资料暂不可用，请稍后重试"); } finally { setBusy(false); }
  }}>{busy ? "读取中" : "加入观察并研究"}</button>{error && <p role="alert" className="mt-2 text-red-700">{error}</p>}</>;
}

function EventEditor({ event, onSaved }: { event: EventDetail; onSaved: (data: EventDetail) => void }) {
  const [plan, setPlan] = useState({ stage: event.stage, plan: event.plan, invalidation: event.invalidation, status: event.status });
  const [record, setRecord] = useState({ kind: "观察", action: "观察", symbol: "", text: "", price: "", quantity: "" });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const requestId = useRef<string | null>(null);
  async function save(path: string, method: string, body: object) {
    setBusy(true); setMessage("");
    try { const data = await request(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); onSaved(data); setMessage("已保存到本地事件档案"); return true; }
    catch (e) { setMessage(String(e)); return false; }
    finally { setBusy(false); }
  }
  return <Card>
    <h4 className="font-semibold">人工阶段与执行计划</h4>
    <p className="mt-2 text-sm leading-7 text-slate-600">{stageHints[plan.stage]}</p>
    <form className="mt-3 space-y-3" onSubmit={async e => { e.preventDefault(); await save(`/${event.id}`, "PATCH", plan); }}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="人工确认阶段"><select className={inputClass} value={plan.stage} onChange={e => setPlan({ ...plan, stage: e.target.value })}>{stages.map(stage => <option key={stage}>{stage}</option>)}</select></Field>
        <Field label="事件状态"><select className={inputClass} value={plan.status} onChange={e => setPlan({ ...plan, status: e.target.value as "active" | "closed" })}><option value="active">继续跟踪</option><option value="closed">结束跟踪</option></select></Field>
      </div>
      <Field label="计划与证据"><textarea maxLength={4000} rows={3} className={inputClass} value={plan.plan} onChange={e => setPlan({ ...plan, plan: e.target.value })} placeholder="记录支持阶段的证据、下一次核验条件、仓位预算和可接受价格。" /></Field>
      <Field label="失效条件"><textarea maxLength={2000} rows={2} className={inputClass} value={plan.invalidation} onChange={e => setPlan({ ...plan, invalidation: e.target.value })} placeholder="什么事实会推翻计划，无法成交时如何处理？" /></Field>
      <button type="submit" className={buttonClass} disabled={busy}>保存阶段与计划</button>
    </form>
    <h4 className="mt-6 border-t pt-4 font-semibold">新增判断或执行记录</h4>
    <form className="mt-3 space-y-3" onSubmit={async e => {
      e.preventDefault();
      requestId.current ??= crypto.randomUUID();
      const ok = await save(`/${event.id}/records`, "POST", {
        ...record, id: requestId.current, price: record.price ? Number(record.price) : null, quantity: record.quantity ? Number(record.quantity) : null,
      });
      if (ok) { requestId.current = null; setRecord({ kind: "观察", action: "观察", symbol: "", text: "", price: "", quantity: "" }); }
    }}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="记录性质"><select className={inputClass} value={record.kind} onChange={e => { requestId.current = null; setRecord({ ...record, kind: e.target.value }); }}>{["观察", "人工确认", "未成交", "模拟成交", "实际成交"].map(kind => <option key={kind}>{kind}</option>)}</select></Field>
        <Field label="记录动作"><select className={inputClass} value={record.action} onChange={e => { requestId.current = null; setRecord({ ...record, action: e.target.value }); }}>{["观察", "买入", "加仓", "减仓", "卖出", "放弃"].map(action => <option key={action}>{action}</option>)}</select></Field>
        <Field label="执行股票代码"><input pattern="[0-9]{6}" maxLength={6} className={inputClass} value={record.symbol} onChange={e => { requestId.current = null; setRecord({ ...record, symbol: e.target.value }); }} /></Field>
        <Field label="成交价（元）"><input type="number" min="0.001" step="0.001" className={inputClass} value={record.price} onChange={e => { requestId.current = null; setRecord({ ...record, price: e.target.value }); }} /></Field>
        <Field label="成交股数"><input type="number" min="1" step="1" className={inputClass} value={record.quantity} onChange={e => { requestId.current = null; setRecord({ ...record, quantity: e.target.value }); }} /></Field>
      </div>
      <Field label="判断或执行说明"><textarea required maxLength={4000} rows={3} className={inputClass} value={record.text} onChange={e => { requestId.current = null; setRecord({ ...record, text: e.target.value }); }} placeholder="写证据和实际结果。选择实际成交时，请按券商成交回报填写。" /></Field>
      <button type="submit" className={secondaryButtonClass} disabled={busy || !record.text.trim()}>保存执行记录</button>
    </form>
    {message && <p role="status" className="mt-3 text-sm text-emerald-800">{message}</p>}
  </Card>;
}
