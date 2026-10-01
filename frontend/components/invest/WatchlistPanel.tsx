"use client";

import { useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";

import { makeId, PersonalInvestmentState, WatchItem } from "@/lib/personal-investment";
import { buttonClass, Card, Empty, Field, inputClass, secondaryButtonClass } from "./ui";

type Props = {
  state: PersonalInvestmentState;
  setState: Dispatch<SetStateAction<PersonalInvestmentState>>;
};

const EMPTY_ITEM: Omit<WatchItem, "id"> = {
  code: "",
  name: "",
  price: 0,
  pe: 0,
  dividendYield: 0,
  qualityScore: 60,
  targetLow: 0,
  targetHigh: 0,
  riskTags: "",
  status: "观察",
};

export default function WatchlistPanel({ state, setState }: Props) {
  const [draft, setDraft] = useState(EMPTY_ITEM);
  const [view, setView] = useState<"table" | "cards">("cards");
  const [filter, setFilter] = useState("全部");

  const visible = useMemo(
    () => state.watchlist.filter((item) => filter === "全部" || item.status === filter),
    [filter, state.watchlist],
  );

  function addItem() {
    if (!draft.code.trim() || !draft.name.trim()) return;
    setState((current) => ({
      ...current,
      watchlist: [...current.watchlist, { ...draft, id: makeId("watch"), code: draft.code.trim() }],
    }));
    setDraft(EMPTY_ITEM);
  }

  function remove(id: string) {
    setState((current) => ({ ...current, watchlist: current.watchlist.filter((item) => item.id !== id) }));
  }

  function zone(item: WatchItem) {
    if (!item.price || !item.targetLow || !item.targetHigh) return { label: "待补数据", cls: "bg-slate-100 text-slate-600" };
    if (item.price >= item.targetLow && item.price <= item.targetHigh) return { label: "进入观察区", cls: "bg-emerald-100 text-emerald-700" };
    if (item.price < item.targetLow) return { label: "低于区间", cls: "bg-sky-100 text-sky-700" };
    const distance = ((item.price - item.targetHigh) / item.targetHigh) * 100;
    return { label: `高于区间 ${distance.toFixed(1)}%`, cls: distance > 20 ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-700" };
  }

  return (
    <div className="space-y-5">
      <Card>
        <div>
          <h2 className="text-lg font-semibold">添加A股观察对象</h2>
          <p className="mt-1 text-sm text-slate-500">数据目前由你手动维护；这样不会把延迟行情误当实时价格。</p>
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <Field label="股票代码"><input className={inputClass} value={draft.code} onChange={(e) => setDraft({ ...draft, code: e.target.value })} placeholder="如 601668" /></Field>
          <Field label="股票名称"><input className={inputClass} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></Field>
          <Field label="当前价格"><input className={inputClass} type="number" step="0.01" value={draft.price || ""} onChange={(e) => setDraft({ ...draft, price: Number(e.target.value) })} /></Field>
          <Field label="市盈率 PE"><input className={inputClass} type="number" step="0.1" value={draft.pe || ""} onChange={(e) => setDraft({ ...draft, pe: Number(e.target.value) })} /></Field>
          <Field label="股息率 %"><input className={inputClass} type="number" step="0.1" value={draft.dividendYield || ""} onChange={(e) => setDraft({ ...draft, dividendYield: Number(e.target.value) })} /></Field>
          <Field label="财务质量 0-100"><input className={inputClass} type="number" min="0" max="100" value={draft.qualityScore} onChange={(e) => setDraft({ ...draft, qualityScore: Number(e.target.value) })} /></Field>
          <Field label="观察区间下限"><input className={inputClass} type="number" step="0.01" value={draft.targetLow || ""} onChange={(e) => setDraft({ ...draft, targetLow: Number(e.target.value) })} /></Field>
          <Field label="观察区间上限"><input className={inputClass} type="number" step="0.01" value={draft.targetHigh || ""} onChange={(e) => setDraft({ ...draft, targetHigh: Number(e.target.value) })} /></Field>
          <Field label="风险标签"><input className={inputClass} value={draft.riskTags} onChange={(e) => setDraft({ ...draft, riskTags: e.target.value })} placeholder="周期、高负债、股东减持" /></Field>
          <Field label="研究状态">
            <select className={inputClass} value={draft.status} onChange={(e) => setDraft({ ...draft, status: e.target.value as WatchItem["status"] })}>
              <option>观察</option><option>接近区间</option><option>已进入区间</option><option>排除</option>
            </select>
          </Field>
        </div>
        <button className={`${buttonClass} mt-4`} onClick={addItem}>加入观察池</button>
      </Card>

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">观察池</h2>
            <p className="mt-1 text-sm text-slate-500">低位仅表示价格位置，是否低估仍需结合盈利质量和估值判断。</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <select className={`${inputClass} w-auto`} value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option>全部</option><option>观察</option><option>接近区间</option><option>已进入区间</option><option>排除</option>
            </select>
            <button className={secondaryButtonClass} onClick={() => setView(view === "cards" ? "table" : "cards")}>{view === "cards" ? "表格视图" : "卡片视图"}</button>
          </div>
        </div>

        {visible.length === 0 ? (
          <div className="mt-4"><Empty>观察池为空。先录入你真正愿意持续跟踪的公司。</Empty></div>
        ) : view === "cards" ? (
          <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {visible.map((item) => {
              const location = zone(item);
              return (
                <article key={item.id} className="rounded-xl border border-slate-200 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div><h3 className="font-semibold">{item.name}</h3><div className="text-xs text-slate-400">{item.code}</div></div>
                    <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${location.cls}`}>{location.label}</span>
                  </div>
                  <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                    <Datum label="现价" value={item.price ? `¥${item.price.toFixed(2)}` : "—"} />
                    <Datum label="PE" value={item.pe ? item.pe.toFixed(1) : "—"} />
                    <Datum label="股息率" value={item.dividendYield ? `${item.dividendYield.toFixed(1)}%` : "—"} />
                    <Datum label="财务质量" value={`${item.qualityScore}/100`} />
                    <Datum label="目标区间" value={item.targetLow && item.targetHigh ? `¥${item.targetLow}–${item.targetHigh}` : "—"} />
                    <Datum label="状态" value={item.status} />
                  </div>
                  <div className="mt-3 text-xs text-slate-500">风险：{item.riskTags || "尚未记录"}</div>
                  <button className={`${secondaryButtonClass} mt-4 w-full`} onClick={() => remove(item.id)}>移除</button>
                </article>
              );
            })}
          </div>
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[850px] text-left text-sm">
              <thead className="border-b text-xs uppercase tracking-wide text-slate-400"><tr><th className="py-2">公司</th><th>现价</th><th>PE</th><th>股息率</th><th>质量</th><th>目标区间</th><th>位置</th><th>风险</th><th /></tr></thead>
              <tbody>{visible.map((item) => { const location = zone(item); return <tr key={item.id} className="border-b border-slate-100"><td className="py-3"><div className="font-medium">{item.name}</div><div className="text-xs text-slate-400">{item.code}</div></td><td>{item.price || "—"}</td><td>{item.pe || "—"}</td><td>{item.dividendYield ? `${item.dividendYield}%` : "—"}</td><td>{item.qualityScore}</td><td>{item.targetLow && item.targetHigh ? `${item.targetLow}–${item.targetHigh}` : "—"}</td><td><span className={`rounded-full px-2 py-1 text-xs ${location.cls}`}>{location.label}</span></td><td>{item.riskTags || "—"}</td><td><button className={secondaryButtonClass} onClick={() => remove(item.id)}>删除</button></td></tr>; })}</tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

function Datum({ label, value }: { label: string; value: string }) {
  return <div><div className="text-xs text-slate-400">{label}</div><div className="mt-0.5 font-medium tabular-nums">{value}</div></div>;
}
