"use client";

import { useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";

import {
  DEFAULT_STATE,
  getDrawdownPct,
  getMarketEnvironment,
  getRiskAdjustedEquityCap,
  getThemeScore,
  makeId,
  MarketEnvironment,
  MarketTheme,
  PersonalInvestmentState,
} from "@/lib/personal-investment";
import { buttonClass, Card, Empty, Field, inputClass, ProgressBar, secondaryButtonClass } from "./ui";

type Props = {
  state: PersonalInvestmentState;
  setState: Dispatch<SetStateAction<PersonalInvestmentState>>;
};

const LEVELS = ["很弱", "偏弱", "中性", "偏强", "很强"];
const ENVIRONMENT_ITEMS: { key: keyof Pick<MarketEnvironment, "trend" | "policy" | "liquidity" | "sentiment">; label: string; description: string }[] = [
  { key: "trend", label: "大盘趋势", description: "指数趋势、市场宽度与关键位置" },
  { key: "policy", label: "政策方向", description: "增量政策、产业支持与落地强度" },
  { key: "liquidity", label: "资金与成交", description: "成交额、增量资金与风险偏好" },
  { key: "sentiment", label: "市场情绪", description: "赚钱效应、涨跌停与高位反馈" },
];

const THEME_ITEMS: { key: keyof Pick<MarketTheme, "policy" | "prosperity" | "capital" | "leadership" | "catalyst">; label: string }[] = [
  { key: "policy", label: "产业政策" },
  { key: "prosperity", label: "行业景气" },
  { key: "capital", label: "资金流向" },
  { key: "leadership", label: "龙头效应" },
  { key: "catalyst", label: "催化事件" },
];

const EMPTY_THEME: Omit<MarketTheme, "id"> = {
  name: "",
  policy: 3,
  prosperity: 3,
  capital: 3,
  leadership: 3,
  catalyst: 3,
  thesis: "",
  risks: "",
};

export default function MarketRadarPanel({ state, setState }: Props) {
  const [showThemeForm, setShowThemeForm] = useState(false);
  const [draft, setDraft] = useState(EMPTY_THEME);
  const marketEnvironment = state.marketEnvironment ?? DEFAULT_STATE.marketEnvironment;
  const marketThemes = state.marketThemes ?? [];
  const environment = useMemo(() => getMarketEnvironment(marketEnvironment), [marketEnvironment]);
  const updatedLabel = marketEnvironment.updatedAt
    ? new Date(marketEnvironment.updatedAt).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })
    : "尚未更新";
  const drawdown = getDrawdownPct(state.profile.peakAssets, state.profile.currentAssets);
  const riskCap = getRiskAdjustedEquityCap(drawdown);
  const isCapped = riskCap < environment.range[1];
  const rankedThemes = useMemo(
    () => [...marketThemes].sort((a, b) => getThemeScore(b) - getThemeScore(a)),
    [marketThemes],
  );

  function updateEnvironment(key: keyof MarketEnvironment, value: string | number) {
    setState((current) => ({
      ...current,
      marketEnvironment: {
        ...(current.marketEnvironment ?? DEFAULT_STATE.marketEnvironment),
        [key]: value,
        updatedAt: new Date().toISOString(),
      },
    }));
  }

  function addTheme() {
    if (!draft.name.trim()) return;
    setState((current) => ({
      ...current,
      marketThemes: [...(current.marketThemes ?? []), { ...draft, id: makeId("theme"), name: draft.name.trim() }],
    }));
    setDraft(EMPTY_THEME);
    setShowThemeForm(false);
  }

  return (
    <div className="space-y-5">
      <div className="grid gap-5 xl:grid-cols-[0.85fr_1.15fr]">
        <Card className="overflow-hidden !bg-[#10281d] text-white">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.15em] text-emerald-300">人工环境判断</p>
              <h2 className="mt-2 text-2xl font-semibold">市场状态 · {environment.label}</h2>
            </div>
            <div className="flex h-20 w-20 shrink-0 items-center justify-center rounded-full border-[7px] border-emerald-400/25 bg-white/5">
              <span className="text-2xl font-semibold tabular-nums">{environment.score}</span>
            </div>
          </div>
          <div className="mt-8 rounded-2xl border border-white/10 bg-white/[0.06] p-5">
            <p className="text-xs text-emerald-100/60">建议权益仓位</p>
            <p className="mt-1 text-3xl font-semibold tracking-tight tabular-nums">
              {isCapped ? `不高于 ${riskCap}%` : `${environment.range[0]}%–${environment.range[1]}%`}
            </p>
            <p className="mt-3 text-sm leading-6 text-emerald-50/75">{environment.action}</p>
          </div>
          {isCapped && <p className="mt-4 rounded-xl bg-amber-300/10 px-3 py-2 text-xs leading-5 text-amber-100">当前回撤 {drawdown.toFixed(1)}%，风险防线优先于市场强弱，已压低仓位上限。</p>}
          <p className="mt-4 text-xs leading-5 text-emerald-100/50">仓位区间是决策约束，不是收益预测；还需结合持仓相关性和单股风险。</p>
        </Card>

        <Card>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div><h2 className="text-lg font-semibold">市场环境四维检查</h2><p className="mt-1 text-sm text-slate-500">每周或市场结构显著变化时更新，不因单日涨跌频繁调整。</p></div>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-500">手工录入 · {updatedLabel}</span>
          </div>
          <div className="mt-5 space-y-4">
            {ENVIRONMENT_ITEMS.map((item) => (
              <div key={item.key} className="grid gap-3 rounded-2xl border border-slate-200/80 p-4 lg:grid-cols-[150px_1fr] lg:items-center">
                <div><p className="text-sm font-semibold text-slate-800">{item.label}</p><p className="mt-0.5 text-xs text-slate-400">{item.description}</p></div>
                <LevelPicker value={marketEnvironment[item.key]} onChange={(value) => updateEnvironment(item.key, value)} />
              </div>
            ))}
          </div>
          <Field label="本周判断依据" hint="记录政策、量能或情绪变化，避免只留下一个分数。">
            <textarea className={`${inputClass} mt-4 min-h-20 resize-y`} value={marketEnvironment.notes} onChange={(event) => updateEnvironment("notes", event.target.value)} placeholder="例：成交额连续三日回升，但高位股亏钱效应仍明显……" />
          </Field>
        </Card>
      </div>

      {showThemeForm && <Card>
        <div><h2 className="text-lg font-semibold">添加候选主线</h2><p className="mt-1 text-sm text-slate-500">方向评分用于比较研究优先级，不替代个股财务质量与估值。</p></div>
        <div className="mt-5 grid gap-4 lg:grid-cols-2">
          <Field label="板块 / 主题名称"><input className={inputClass} value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="如：高股息央企、半导体设备" /></Field>
          <Field label="核心逻辑"><input className={inputClass} value={draft.thesis} onChange={(event) => setDraft({ ...draft, thesis: event.target.value })} placeholder="景气与资金为什么可能延续？" /></Field>
        </div>
        <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          {THEME_ITEMS.map((item) => <div key={item.key}><p className="mb-2 text-xs font-medium text-slate-600">{item.label}</p><LevelPicker compact value={draft[item.key]} onChange={(value) => setDraft({ ...draft, [item.key]: value })} /></div>)}
        </div>
        <Field label="主要反向风险"><textarea className={`${inputClass} mt-4 min-h-20 resize-y`} value={draft.risks} onChange={(event) => setDraft({ ...draft, risks: event.target.value })} placeholder="政策不及预期、景气见顶、资金撤离、龙头破位……" /></Field>
        <div className="mt-4 flex gap-2"><button className={buttonClass} onClick={addTheme}>保存主线</button><button className={secondaryButtonClass} onClick={() => setShowThemeForm(false)}>取消</button></div>
      </Card>}

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div><h2 className="text-lg font-semibold">主线候选排序</h2><p className="mt-1 text-sm text-slate-500">看政策、景气、资金、龙头与催化是否形成共振。</p></div>
          <button className={buttonClass} onClick={() => setShowThemeForm((show) => !show)}>{showThemeForm ? "收起录入" : "添加候选主线"}</button>
        </div>
        {rankedThemes.length === 0 ? <div className="mt-5"><Empty>尚未建立主线候选。先添加你准备持续跟踪的两个方向。</Empty></div> : <div className="mt-5 grid gap-4 lg:grid-cols-2">
          {rankedThemes.map((theme) => {
            const score = getThemeScore(theme);
            const label = score >= 70 ? "重点跟踪" : score >= 55 ? "继续观察" : "等待共振";
            return <article key={theme.id} className="rounded-2xl border border-slate-200 p-5">
              <div className="flex items-start justify-between gap-4"><div><h3 className="font-semibold text-slate-900">{theme.name}</h3><p className="mt-1 text-xs text-slate-500">{label}</p></div><span className="text-2xl font-semibold text-[#173f2c] tabular-nums">{score}</span></div>
              <div className="mt-4"><ProgressBar value={score} /></div>
              <div className="mt-4 grid grid-cols-5 gap-2">{THEME_ITEMS.map((item) => <div key={item.key} className="text-center"><p className="text-[11px] text-slate-400">{item.label}</p><p className="mt-1 text-sm font-semibold">{theme[item.key]}/5</p></div>)}</div>
              {theme.thesis && <p className="mt-4 text-sm leading-6 text-slate-600">{theme.thesis}</p>}
              {theme.risks && <p className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">风险：{theme.risks}</p>}
              <button className={`${secondaryButtonClass} mt-4 w-full`} onClick={() => setState((current) => ({ ...current, marketThemes: (current.marketThemes ?? []).filter((item) => item.id !== theme.id) }))}>移除</button>
            </article>;
          })}
        </div>}
      </Card>
    </div>
  );
}

function LevelPicker({ value, onChange, compact = false }: { value: number; onChange: (value: number) => void; compact?: boolean }) {
  if (compact) {
    return <select className={inputClass} value={value} onChange={(event) => onChange(Number(event.target.value))}>{LEVELS.map((label, index) => <option key={label} value={index + 1}>{label}</option>)}</select>;
  }
  return <div className="grid grid-cols-5 gap-1.5">
    {LEVELS.map((label, index) => <button key={label} type="button" onClick={() => onChange(index + 1)} className={`rounded-lg border px-2 py-2 text-xs font-medium transition ${value === index + 1 ? "border-emerald-700 bg-emerald-50 text-emerald-800" : "border-slate-200 bg-white text-slate-500 hover:border-slate-300"}`}>{label}</button>)}
  </div>;
}
