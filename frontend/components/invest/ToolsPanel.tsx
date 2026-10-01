"use client";

import { useMemo, useState } from "react";

import { positionShock, valuationScenarios } from "@/lib/personal-investment";
import { Card, Field, inputClass, Metric, money, ProgressBar } from "./ui";

export default function ToolsPanel({ totalAssets }: { totalAssets: number }) {
  const [positionPct, setPositionPct] = useState(5);
  const [lossPct, setLossPct] = useState(20);
  const [valuation, setValuation] = useState({ currentEps: 2, years: 3, growthPct: 8, pe: 12, dividendYieldPct: 4 });
  const shock = useMemo(() => positionShock(totalAssets, positionPct, lossPct), [lossPct, positionPct, totalAssets]);
  const scenarios = useMemo(() => valuationScenarios(valuation), [valuation]);

  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <Card>
        <div>
          <h2 className="text-lg font-semibold">仓位冲击模拟器</h2>
          <p className="mt-1 text-sm text-slate-500">拖动滑块，观察单只股票下跌对整个账户的真实影响。</p>
        </div>

        <div className="mt-6 space-y-6">
          <Range label="单只股票仓位" value={positionPct} min={1} max={40} suffix="%" onChange={setPositionPct} />
          <Range label="个股下跌幅度" value={lossPct} min={1} max={80} suffix="%" onChange={setLossPct} />
        </div>

        <div className="mt-6 grid grid-cols-2 gap-3">
          <Metric label="该仓位市值" value={money(shock.positionValue)} />
          <Metric label="亏损金额" value={money(shock.lossAmount)} tone="danger" />
          <Metric label="组合损失" value={`${shock.portfolioLossPct.toFixed(2)}%`} tone={shock.portfolioLossPct > 4 ? "danger" : shock.portfolioLossPct > 2 ? "warn" : "good"} />
          <Metric label="冲击后资产" value={money(shock.remainingAssets)} />
        </div>

        <div className="mt-5 rounded-xl bg-slate-50 p-4">
          <div className="flex justify-between text-sm"><span>20%总回撤预算占用</span><span className="font-medium">{((shock.portfolioLossPct / 20) * 100).toFixed(0)}%</span></div>
          <div className="mt-2"><ProgressBar value={(shock.portfolioLossPct / 20) * 100} color={shock.portfolioLossPct > 4 ? "bg-red-500" : "bg-emerald-500"} /></div>
          <p className="mt-3 text-xs text-slate-500">5%仓位即使下跌40%，组合损失约2%；30%仓位同样下跌会损失12%。</p>
        </div>
      </Card>

      <Card>
        <div>
          <h2 className="text-lg font-semibold">估值情景计算器</h2>
          <p className="mt-1 text-sm text-slate-500">这是假设实验器，不是目标价预测。结果取决于输入质量。</p>
        </div>

        <div className="mt-5 grid grid-cols-2 gap-3">
          <Field label="当前每股收益 EPS"><input className={inputClass} type="number" step="0.01" value={valuation.currentEps} onChange={(e) => setValuation({ ...valuation, currentEps: Number(e.target.value) })} /></Field>
          <Field label="估值年数"><input className={inputClass} type="number" min="1" max="10" value={valuation.years} onChange={(e) => setValuation({ ...valuation, years: Number(e.target.value) })} /></Field>
        </div>
        <div className="mt-5 space-y-5">
          <Range label="中性利润增速" value={valuation.growthPct} min={-15} max={30} suffix="%" onChange={(value) => setValuation({ ...valuation, growthPct: value })} />
          <Range label="中性估值倍数" value={valuation.pe} min={4} max={40} suffix="×" onChange={(value) => setValuation({ ...valuation, pe: value })} />
          <Range label="预期股息率" value={valuation.dividendYieldPct} min={0} max={12} suffix="%" step={0.5} onChange={(value) => setValuation({ ...valuation, dividendYieldPct: value })} />
        </div>

        <div className="mt-6 grid gap-3 sm:grid-cols-3">
          <ScenarioCard label="悲观" value={scenarios.bear.totalValue} detail={`增速 ${scenarios.bear.growthPct}% · PE ${scenarios.bear.pe}×`} tone="border-red-200 bg-red-50" />
          <ScenarioCard label="中性" value={scenarios.base.totalValue} detail={`增速 ${scenarios.base.growthPct}% · PE ${scenarios.base.pe}×`} tone="border-emerald-200 bg-emerald-50" />
          <ScenarioCard label="乐观" value={scenarios.bull.totalValue} detail={`增速 ${scenarios.bull.growthPct}% · PE ${scenarios.bull.pe}×`} tone="border-sky-200 bg-sky-50" />
        </div>
        <p className="mt-4 text-xs leading-relaxed text-slate-500">情景总价值 = 期末EPS × 估值倍数 + 粗略累计分红。未考虑稀释、周期峰谷、资本开支和贴现率，正式估值时仍需个别建模。</p>
      </Card>
    </div>
  );
}

function Range({ label, value, min, max, suffix, step = 1, onChange }: { label: string; value: number; min: number; max: number; suffix: string; step?: number; onChange: (value: number) => void }) {
  return (
    <label className="block">
      <div className="mb-2 flex items-center justify-between text-sm"><span className="font-medium text-slate-600">{label}</span><span className="rounded-md bg-slate-100 px-2 py-1 font-semibold tabular-nums">{value}{suffix}</span></div>
      <input className="h-2 w-full cursor-pointer appearance-none rounded-full bg-slate-200 accent-emerald-600" type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} />
      <div className="mt-1 flex justify-between text-xs text-slate-400"><span>{min}{suffix}</span><span>{max}{suffix}</span></div>
    </label>
  );
}

function ScenarioCard({ label, value, detail, tone }: { label: string; value: number; detail: string; tone: string }) {
  return <div className={`rounded-xl border p-4 ${tone}`}><div className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</div><div className="mt-1 text-2xl font-semibold tabular-nums">¥{value.toFixed(2)}</div><div className="mt-1 text-xs text-slate-500">{detail}</div></div>;
}
