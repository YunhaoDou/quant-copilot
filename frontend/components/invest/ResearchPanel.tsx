"use client";

import { useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";

import { makeId, PersonalInvestmentState, ResearchNote } from "@/lib/personal-investment";
import { buttonClass, Card, Empty, Field, inputClass, secondaryButtonClass } from "./ui";

type Props = {
  state: PersonalInvestmentState;
  setState: Dispatch<SetStateAction<PersonalInvestmentState>>;
};

const EMPTY_NOTE: Omit<ResearchNote, "id" | "updatedAt"> = {
  code: "",
  name: "",
  businessModel: "",
  financialTrend: "",
  valuationThesis: "",
  catalysts: "",
  bearCase: "",
  invalidation: "",
};

export default function ResearchPanel({ state, setState }: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(state.research[0]?.id ?? null);
  const selected = useMemo(() => state.research.find((item) => item.id === selectedId) ?? null, [selectedId, state.research]);
  const [draft, setDraft] = useState(EMPTY_NOTE);

  function createNote() {
    if (!draft.code.trim() || !draft.name.trim()) return;
    const note: ResearchNote = { ...draft, id: makeId("research"), updatedAt: new Date().toISOString() };
    setState((current) => ({ ...current, research: [...current.research, note] }));
    setSelectedId(note.id);
    setDraft(EMPTY_NOTE);
  }

  function update(field: keyof Omit<ResearchNote, "id" | "updatedAt">, value: string) {
    if (!selected) return;
    setState((current) => ({
      ...current,
      research: current.research.map((item) => item.id === selected.id ? { ...item, [field]: value, updatedAt: new Date().toISOString() } : item),
    }));
  }

  return (
    <div className="grid gap-5 xl:grid-cols-[300px_1fr]">
      <div className="space-y-5">
        <Card>
          <h2 className="text-lg font-semibold">新建研究档案</h2>
          <div className="mt-4 space-y-3">
            <Field label="代码"><input className={inputClass} value={draft.code} onChange={(e) => setDraft({ ...draft, code: e.target.value })} placeholder="如 601668" /></Field>
            <Field label="公司名称"><input className={inputClass} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></Field>
            <button className={`${buttonClass} w-full`} onClick={createNote}>创建研究档案</button>
          </div>
        </Card>

        <Card>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">研究对象</h2>
          <div className="mt-3 space-y-2">
            {state.research.length === 0 ? <Empty>还没有研究档案。</Empty> : state.research.map((item) => (
              <button
                key={item.id}
                onClick={() => setSelectedId(item.id)}
                className={`w-full rounded-lg border px-3 py-2 text-left transition ${selectedId === item.id ? "border-emerald-400 bg-emerald-50" : "border-slate-200 hover:bg-slate-50"}`}
              >
                <div className="text-sm font-medium">{item.name}</div>
                <div className="text-xs text-slate-400">{item.code}</div>
              </button>
            ))}
          </div>
        </Card>
      </div>

      <Card>
        {!selected ? (
          <Empty>从左侧新建或选择一家公司，开始填写完整投资论证。</Empty>
        ) : (
          <div>
            <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 pb-4">
              <div>
                <h2 className="text-xl font-semibold">{selected.name} <span className="font-normal text-slate-400">{selected.code}</span></h2>
                <p className="mt-1 text-xs text-slate-400">自动保存 · 最近更新 {new Date(selected.updatedAt).toLocaleString("zh-CN")}</p>
              </div>
              <button
                className={secondaryButtonClass}
                onClick={() => {
                  setState((current) => ({ ...current, research: current.research.filter((item) => item.id !== selected.id) }));
                  setSelectedId(null);
                }}
              >删除档案</button>
            </div>

            <div className="mt-5 grid gap-4 lg:grid-cols-2">
              <LongField label="商业模式" value={selected.businessModel} onChange={(value) => update("businessModel", value)} placeholder="谁付钱、为什么付钱、公司如何获得现金流？" />
              <LongField label="财务趋势" value={selected.financialTrend} onChange={(value) => update("financialTrend", value)} placeholder="收入、扣非利润、现金流、ROE、负债和关键异常。" />
              <LongField label="估值情景" value={selected.valuationThesis} onChange={(value) => update("valuationThesis", value)} placeholder="悲观、中性、乐观假设与合理价值区间。" />
              <LongField label="潜在催化剂" value={selected.catalysts} onChange={(value) => update("catalysts", value)} placeholder="业绩、供需、治理、分红或行业变化。" />
              <LongField label="反方观点" value={selected.bearCase} onChange={(value) => update("bearCase", value)} placeholder="最有力的看空理由是什么？哪些数据支持它？" />
              <LongField label="逻辑失效条件" value={selected.invalidation} onChange={(value) => update("invalidation", value)} placeholder="出现哪些可观察事实时必须重估或退出？" danger />
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}

function LongField({ label, value, onChange, placeholder, danger = false }: { label: string; value: string; onChange: (value: string) => void; placeholder: string; danger?: boolean }) {
  return (
    <Field label={label}>
      <textarea
        className={`${inputClass} min-h-36 resize-y ${danger ? "border-red-200 focus:border-red-500 focus:ring-red-100" : ""}`}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
      />
    </Field>
  );
}
