"use client";

import { useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";

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
  { key: "stable" as const, label: "稳健资产", color: "bg-sky-500" },
  { key: "index" as const, label: "宽基指数", color: "bg-indigo-500" },
  { key: "stocks" as const, label: "研究型个股", color: "bg-emerald-500" },
  { key: "cash" as const, label: "投资现金", color: "bg-amber-500" },
];

export default function DashboardPanel({ state, setState }: Props) {
  const [showHoldingForm, setShowHoldingForm] = useState(false);
  const [holding, setHolding] = useState({ code: "", name: "", marketValue: 0, cost: 0, thesis: "" });
  const risk = useMemo(() => getRiskBudget(state.profile), [state.profile]);
  const holdingsValue = state.holdings.reduce((sum, item) => sum + item.marketValue, 0);
  const holdingsPnl = state.holdings.reduce((sum, item) => sum + item.marketValue - item.cost, 0);
  const monthlyAnnual = state.profile.monthlyContribution * 12;

  function updateProfile(key: "initialCapital" | "monthlyContribution" | "peakAssets" | "currentAssets" | "maxDrawdownPct", value: number) {
    setState((current) => ({
      ...current,
      profile: { ...current.profile, [key]: Math.max(0, value || 0) },
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

  function addHolding() {
    if (!holding.code.trim() || !holding.name.trim()) return;
    setState((current) => ({
      ...current,
      holdings: [...current.holdings, { id: makeId("holding"), ...holding, code: holding.code.trim() }],
    }));
    setHolding({ code: "", name: "", marketValue: 0, cost: 0, thesis: "" });
    setShowHoldingForm(false);
  }

  return (
    <div className="space-y-5">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Metric label="当前总资产" value={money(state.profile.currentAssets)} hint={`初始本金 ${money(state.profile.initialCapital)}`} />
        <Metric label="年度新增资金" value={money(monthlyAnnual)} hint={`每月 ${money(state.profile.monthlyContribution)}`} />
        <Metric
          label="当前回撤"
          value={`${risk.drawdownPct.toFixed(1)}%`}
          hint={`20%防线剩余 ${money(risk.remaining)}`}
          tone={risk.drawdownPct >= 18 ? "danger" : risk.drawdownPct >= 10 ? "warn" : "good"}
        />
        <Metric
          label="持仓浮动盈亏"
          value={money(holdingsPnl)}
          hint={`持仓市值 ${money(holdingsValue)}`}
          tone={holdingsPnl >= 0 ? "good" : "danger"}
        />
      </div>

      <Card className={`border ${risk.stage.background}`}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className={`text-sm font-semibold ${risk.stage.color}`}>20%回撤防线 · {risk.stage.level}</div>
            <p className="mt-1 text-sm text-slate-600">{risk.stage.instruction}</p>
          </div>
          <div className="min-w-52 text-right text-sm tabular-nums text-slate-600">
            已消耗 {money(risk.currentLoss)} / 最大 {money(risk.maxLoss)}
          </div>
        </div>
        <div className="mt-4">
          <ProgressBar
            value={state.profile.maxDrawdownPct ? (risk.drawdownPct / state.profile.maxDrawdownPct) * 100 : 100}
            color={risk.drawdownPct >= 18 ? "bg-red-500" : risk.drawdownPct >= 10 ? "bg-amber-500" : "bg-emerald-500"}
          />
        </div>
      </Card>

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
          <div className="mt-5 space-y-4">
            {ALLOCATION_META.map((item) => {
              const pct = state.profile.allocations[item.key];
              return (
                <div key={item.key} className="grid grid-cols-[88px_1fr_72px] items-center gap-3">
                  <span className="text-sm text-slate-600">{item.label}</span>
                  <ProgressBar value={pct} color={item.color} />
                  <div className="relative">
                    <input
                      className={`${inputClass} py-1.5 pr-7 text-right tabular-nums`}
                      type="number"
                      min="0"
                      max="100"
                      value={pct}
                      onChange={(event) => updateAllocation(item.key, Number(event.target.value))}
                    />
                    <span className="pointer-events-none absolute right-2 top-1.5 text-sm text-slate-400">%</span>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>

        <Card>
          <h2 className="text-lg font-semibold">个人参数</h2>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <Field label="初始本金">
              <input className={inputClass} type="number" value={state.profile.initialCapital} onChange={(e) => updateProfile("initialCapital", Number(e.target.value))} />
            </Field>
            <Field label="每月新增">
              <input className={inputClass} type="number" value={state.profile.monthlyContribution} onChange={(e) => updateProfile("monthlyContribution", Number(e.target.value))} />
            </Field>
            <Field label="历史峰值资产">
              <input className={inputClass} type="number" value={state.profile.peakAssets} onChange={(e) => updateProfile("peakAssets", Number(e.target.value))} />
            </Field>
            <Field label="当前资产">
              <input className={inputClass} type="number" value={state.profile.currentAssets} onChange={(e) => updateProfile("currentAssets", Number(e.target.value))} />
            </Field>
            <Field label="最大回撤上限">
              <input className={inputClass} type="number" min="1" max="100" value={state.profile.maxDrawdownPct} onChange={(e) => updateProfile("maxDrawdownPct", Number(e.target.value))} />
            </Field>
          </div>
        </Card>
      </div>

      <Card>
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">实际持仓</h2>
            <p className="mt-1 text-sm text-slate-500">手动记录真实持仓；本系统不会连接券商或自动下单。</p>
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
