"use client";

import { useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { useLiveQuotes } from "@/lib/live-market";
import BrokerReadonly from "./broker-readonly";

import {
  getRiskBudget,
  makeId,
  PersonalInvestmentState,
} from "@/lib/personal-investment";
import {
  buttonClass,
  Card,
  Empty,
  Field,
  inputClass,
  Metric,
  money,
  ProgressBar,
  secondaryButtonClass,
} from "./ui";

type Props = {
  state: PersonalInvestmentState;
  setState: Dispatch<SetStateAction<PersonalInvestmentState>>;
};

const ALLOCATION_META = [
  { key: "stable" as const, label: "稳健资产", color: "bg-sky-500", hex: "#0ea5e9" },
  { key: "index" as const, label: "宽基指数", color: "bg-indigo-500", hex: "#6366f1" },
  { key: "stocks" as const, label: "研究型个股", color: "bg-emerald-500", hex: "#10b981" },
  { key: "cash" as const, label: "投资现金", color: "bg-amber-500", hex: "#f59e0b" },
];

export default function DashboardPanel({ state: recordedState, setState }: Props) {
  const quotes = useLiveQuotes(recordedState.holdings.map(h => h.code));
  const state = { ...recordedState, holdings: recordedState.holdings.map(h => {
    const q = quotes.data?.quotes.find(q => q.code === h.code.replace(/\D/g, "").slice(0, 6));
    return q && h.quantity != null ? { ...h, marketValue: h.quantity*q.price } : h;
  }) };
  const [showHoldingForm, setShowHoldingForm] = useState(false);
  const [showProfile, setShowProfile] = useState(false);
  const [holding, setHolding] = useState({ code: "", name: "", marketValue: 0, cost: 0, quantity: 0, thesis: "" });
  const risk = useMemo(() => getRiskBudget(state.profile), [state.profile]);
  const holdingsValue = state.holdings.reduce((sum, item) => sum + item.marketValue, 0);
  const holdingsPnl = state.holdings.reduce((sum, item) => sum + item.marketValue - item.cost, 0);
  const monthlyAnnual = state.profile.monthlyContribution * 12;

  function updateProfile(key: "initialCapital" | "monthlyContribution" | "peakAssets" | "currentAssets" | "maxDrawdownPct", value: number) {
    setState((current) => ({
      ...current,
      profile: { ...current.profile, [key]: key === "maxDrawdownPct" ? Math.min(100, Math.max(1, value || 1)) : Math.max(0, value || 0) },
    }));
  }

  function updateAllocation(key: "stable" | "index" | "stocks" | "cash", value: number) {
    setState((current) => ({
      ...current,
      profile: {
        ...current.profile,
        allocations: { ...current.profile.allocations, [key]: Math.max(0, Math.min(100, value || 0)) },
      },
    }));
  }

  const allocationTotal = Object.values(state.profile.allocations).reduce((sum, item) => sum + item, 0);
  let allocationCursor = 0;
  const allocationStops = ALLOCATION_META.map((item) => {
    const start = allocationCursor;
    allocationCursor += state.profile.allocations[item.key];
    return `${item.hex} ${start}% ${Math.min(100, allocationCursor)}%`;
  });
  if (allocationCursor < 100) allocationStops.push(`#e2e8f0 ${allocationCursor}% 100%`);
  const allocationGradient = `conic-gradient(${allocationStops.join(", ")})`;
  const capitalChange = state.profile.currentAssets - state.profile.initialCapital;

  function addHolding() {
    if (!holding.code.trim() || !holding.name.trim()) return;
    setState((current) => ({
      ...current,
      holdings: [...current.holdings, { id: makeId("holding"), ...holding, quantity: holding.quantity > 0 ? holding.quantity : undefined, code: holding.code.trim() }],
    }));
    setHolding({ code: "", name: "", marketValue: 0, cost: 0, quantity: 0, thesis: "" });
    setShowHoldingForm(false);
  }

  return (
    <div className="space-y-5">
      <div className="grid gap-5 xl:grid-cols-[1.45fr_0.85fr]">
        <Card className="overflow-hidden p-0">
          <div className="border-b border-slate-100 p-6 sm:p-7">
            <div className="flex flex-wrap items-start justify-between gap-5">
              <div>
                <p className="text-sm font-medium text-slate-500">当前总资产</p>
                <p className="mt-2 text-4xl font-semibold tracking-[-0.04em] text-slate-950 tabular-nums sm:text-5xl">
                  {money(state.profile.currentAssets)}
                </p>
                <p className={`mt-2 text-sm ${capitalChange >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                  资产差额（含入金，非投资收益） {capitalChange >= 0 ? "+" : ""}{money(capitalChange)}
                </p>
              </div>
              <div className="rounded-2xl bg-[#edf5ef] px-4 py-3 text-right">
                <p className="text-xs font-medium text-[#3b6750]">年度计划投入</p>
                <p className="mt-1 font-semibold text-[#173f2c] tabular-nums">{money(monthlyAnnual)}</p>
                <p className="mt-0.5 text-xs text-[#5f7d6b]">每月 {money(state.profile.monthlyContribution)}</p>
              </div>
            </div>
          </div>
          <div className="grid gap-3 p-5 sm:grid-cols-3 sm:p-6">
            <Metric label="持仓参考市值" value={money(holdingsValue)} hint={`${state.holdings.length} 只证券 · 有股数按真实报价估值`} />
            <Metric label="持仓浮盈亏" value={money(holdingsPnl)} hint="按手动录入成本" tone={holdingsPnl >= 0 ? "good" : "danger"} />
            <Metric label="当前回撤" value={`${risk.drawdownPct.toFixed(1)}%`} hint={`峰值 ${money(state.profile.peakAssets)}`} tone={risk.drawdownPct >= risk.limit * 0.9 ? "danger" : risk.drawdownPct >= risk.limit * 0.5 ? "warn" : "good"} />
          </div>
        </Card>

        <Card className={`${risk.stage.background} flex flex-col justify-between`}>
          <div>
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-semibold text-slate-700">{risk.limit}% 回撤防线</p>
              <span className={`rounded-full bg-white/80 px-3 py-1 text-xs font-semibold ${risk.stage.color}`}>{risk.stage.level}</span>
            </div>
            <p className="mt-6 text-sm text-slate-500">剩余风险预算</p>
            <p className="mt-1 text-3xl font-semibold tracking-tight text-slate-950 tabular-nums">{money(risk.remaining)}</p>
            <p className="mt-2 text-xs text-slate-500">已消耗 {money(risk.currentLoss)} / 最大 {money(risk.maxLoss)}</p>
            <div className="mt-5">
              <ProgressBar value={risk.drawdownPct / risk.limit * 100} color={risk.drawdownPct >= risk.limit * 0.9 ? "bg-red-500" : risk.drawdownPct >= risk.limit * 0.5 ? "bg-amber-500" : "bg-emerald-500"} />
              <div className="mt-2 flex flex-wrap justify-between gap-2 text-[11px] text-slate-500"><span>观察 {+(risk.limit * 0.5).toFixed(2)}%</span><span>收缩 {+(risk.limit * 0.75).toFixed(2)}%</span><span>防守 {+(risk.limit * 0.9).toFixed(2)}%</span><span>触线 {risk.limit}%</span></div>
            </div>
          </div>
          <div className="mt-6 rounded-2xl border border-white/80 bg-white/65 p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">当前动作</p>
            <p className="mt-2 text-sm font-medium leading-6 text-slate-700">{risk.stage.instruction}</p>
          </div>
        </Card>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.25fr_0.75fr]">
        <Card>
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold">资产配置</h2>
              <p className="mt-1 text-sm text-slate-500">调整目标比例，合计应为100%。</p>
            </div>
            <span className={`rounded-full px-3 py-1 text-sm font-medium ${allocationTotal === 100 ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"}`}>
              合计 {allocationTotal}%
            </span>
          </div>
          <div className="mt-6 grid items-center gap-7 md:grid-cols-[180px_1fr]">
            <div className="mx-auto flex h-40 w-40 items-center justify-center rounded-full" style={{ background: allocationGradient }}>
              <div className="flex h-28 w-28 flex-col items-center justify-center rounded-full bg-white shadow-inner">
                <span className="text-xs text-slate-400">目标合计</span>
                <span className="mt-1 text-2xl font-semibold text-slate-900 tabular-nums">{allocationTotal}%</span>
              </div>
            </div>
            <div className="space-y-3">
              {ALLOCATION_META.map((item) => {
                const pct = state.profile.allocations[item.key];
                return (
                  <div key={item.key} className="grid grid-cols-[100px_1fr_70px] items-center gap-3">
                    <span className="flex items-center gap-2 text-sm text-slate-600"><i className={`h-2.5 w-2.5 rounded-full ${item.color}`} />{item.label}</span>
                    <ProgressBar value={pct} color={item.color} />
                    <div className="relative">
                      <input className={`${inputClass} py-1.5 pr-7 text-right tabular-nums`} type="number" min="0" max="100" value={pct} onChange={(event) => updateAllocation(item.key, Number(event.target.value))} />
                      <span className="pointer-events-none absolute right-2 top-1.5 text-sm text-slate-400">%</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </Card>

        <Card>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-700">本月重点</p>
          <h2 className="mt-2 text-xl font-semibold tracking-tight">先守住风险预算，再寻找赔率</h2>
          <p className="mt-2 text-sm leading-6 text-slate-500">你的新增资金能力稳定，不需要用集中押注换取速度。优先完善观察池证据和退出条件。</p>
          <div className="mt-5 grid grid-cols-2 gap-3">
            <div className="rounded-2xl bg-slate-50 p-4"><p className="text-xs text-slate-500">回撤阶段</p><p className={`mt-1 text-xl font-semibold ${risk.stage.color}`}>{risk.stage.level}</p></div>
            <div className="rounded-2xl bg-slate-50 p-4"><p className="text-xs text-slate-500">计划权益比例 · 手工目标</p><p className="mt-1 text-xl font-semibold tabular-nums">{state.profile.allocations.index + state.profile.allocations.stocks}%</p></div>
            <div className="rounded-2xl bg-slate-50 p-4"><p className="text-xs text-slate-500">最大单股建议</p><p className="mt-1 text-xl font-semibold tabular-nums">8%</p></div>
            <div className="rounded-2xl bg-slate-50 p-4"><p className="text-xs text-slate-500">紧急备用金</p><p className="mt-1 text-xl font-semibold tabular-nums">3 个月</p></div>
          </div>
          <button className={`${secondaryButtonClass} mt-5 w-full`} onClick={() => setShowProfile((show) => !show)}>{showProfile ? "收起个人参数" : "调整个人参数"}</button>
          {showProfile && <div className="mt-4 grid grid-cols-2 gap-3 rounded-2xl bg-slate-50 p-4">
            <Field label="初始本金"><input className={inputClass} type="number" value={state.profile.initialCapital} onChange={(e) => updateProfile("initialCapital", Number(e.target.value))} /></Field>
            <Field label="每月新增"><input className={inputClass} type="number" value={state.profile.monthlyContribution} onChange={(e) => updateProfile("monthlyContribution", Number(e.target.value))} /></Field>
            <Field label="历史峰值"><input className={inputClass} type="number" value={state.profile.peakAssets} onChange={(e) => updateProfile("peakAssets", Number(e.target.value))} /></Field>
            <Field label="当前资产"><input className={inputClass} type="number" value={state.profile.currentAssets} onChange={(e) => updateProfile("currentAssets", Number(e.target.value))} /></Field>
            <Field label="回撤上限"><input className={inputClass} type="number" min="1" max="100" value={state.profile.maxDrawdownPct} onChange={(e) => updateProfile("maxDrawdownPct", Number(e.target.value))} /></Field>
          </div>}
        </Card>
      </div>

      <BrokerReadonly state={recordedState} setState={setState} />
      <Card>
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">实际持仓</h2>
            <p className="mt-1 text-sm text-slate-500">已导入股数的持仓按腾讯真实报价估值，其余为手工快照。总资产和资金仍以券商查询为准。</p>
            <p className="mt-1 text-xs text-slate-400">{quotes.error || (quotes.data ? `行情获取于${new Date(quotes.data.fetched_at).toLocaleString("zh-CN")}` : "尚无最新报价，市值为已录入快照")}</p>
          </div>
          <button className={buttonClass} onClick={() => setShowHoldingForm((show) => !show)}>
            {showHoldingForm ? "收起" : "添加持仓"}
          </button>
        </div>

        {showHoldingForm && (
          <div className="mt-4 grid gap-3 rounded-xl bg-slate-50 p-4 md:grid-cols-2 xl:grid-cols-5">
            <Field label="代码"><input className={inputClass} value={holding.code} onChange={(e) => setHolding({ ...holding, code: e.target.value })} placeholder="如 601668" /></Field>
            <Field label="名称"><input className={inputClass} value={holding.name} onChange={(e) => setHolding({ ...holding, name: e.target.value })} /></Field>
            <Field label="当前市值"><input className={inputClass} type="number" value={holding.marketValue || ""} onChange={(e) => setHolding({ ...holding, marketValue: Number(e.target.value) })} /></Field>
            <Field label="持仓成本"><input className={inputClass} type="number" value={holding.cost || ""} onChange={(e) => setHolding({ ...holding, cost: Number(e.target.value) })} /></Field>
            <Field label="持仓股数（填写后按报价估值）"><input className={inputClass} type="number" min="0" step="1" value={holding.quantity || ""} onChange={(e) => setHolding({ ...holding, quantity: Number(e.target.value) })} /></Field>
            <Field label="一句话逻辑"><input className={inputClass} value={holding.thesis} onChange={(e) => setHolding({ ...holding, thesis: e.target.value })} /></Field>
            <button className={`${buttonClass} md:col-span-2 xl:col-span-5`} onClick={addHolding}>保存持仓</button>
          </div>
        )}

        <div className="mt-4 overflow-x-auto">
          {state.holdings.length === 0 ? (
            <Empty>尚未录入持仓。添加后会自动计算组合市值和浮动盈亏。</Empty>
          ) : (
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="border-b text-xs uppercase tracking-wide text-slate-400">
                <tr><th className="py-2">代码/名称</th><th>市值</th><th>成本</th><th>盈亏</th><th>组合权重</th><th>投资逻辑</th><th /></tr>
              </thead>
              <tbody>
                {state.holdings.map((item) => {
                  const pnl = item.marketValue - item.cost;
                  const weight = state.profile.currentAssets > 0 ? (item.marketValue / state.profile.currentAssets) * 100 : 0;
                  return (
                    <tr key={item.id} className="border-b border-slate-100 last:border-0">
                      <td className="py-3"><div className="font-medium">{item.name}</div><div className="text-xs text-slate-400">{item.code}</div></td>
                      <td className="tabular-nums">{money(item.marketValue)}</td>
                      <td className="tabular-nums">{money(item.cost)}</td>
                      <td className={`tabular-nums ${pnl >= 0 ? "text-emerald-700" : "text-red-700"}`}>{money(pnl)}</td>
                      <td className={`tabular-nums ${weight > 8 ? "font-semibold text-red-700" : ""}`}>{weight.toFixed(1)}%</td>
                      <td className="max-w-xs text-slate-600">{item.thesis || "—"}</td>
                      <td><button className={secondaryButtonClass} onClick={() => setState((current) => ({ ...current, holdings: current.holdings.filter((holdingItem) => holdingItem.id !== item.id) }))}>删除</button></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </Card>
    </div>
  );
}
