"use client";

import { useState } from "react";
import type { Dispatch, SetStateAction } from "react";

import { DecisionEntry, makeId, PersonalInvestmentState } from "@/lib/personal-investment";
import { buttonClass, Card, Empty, Field, inputClass, money, secondaryButtonClass } from "./ui";

type Props = {
  state: PersonalInvestmentState;
  setState: Dispatch<SetStateAction<PersonalInvestmentState>>;
};

const today = () => new Date().toISOString().slice(0, 10);

const EMPTY: Omit<DecisionEntry, "id"> = {
  date: today(),
  code: "",
  action: "观察",
  amount: 0,
  reason: "",
  evidence: "",
  risks: "",
  exitCondition: "",
  lesson: "",
};

export default function JournalPanel({ state, setState }: Props) {
  const [draft, setDraft] = useState(EMPTY);

  function save() {
    if (!draft.code.trim() || !draft.reason.trim()) return;
    setState((current) => ({ ...current, journal: [{ ...draft, id: makeId("decision") }, ...current.journal] }));
    setDraft({ ...EMPTY, date: today() });
  }

  return (
    <div className="space-y-5">
      <Card>
        <div>
          <h2 className="text-lg font-semibold">记录一次投资决策</h2>
          <p className="mt-1 text-sm text-slate-500">先写证据和退出条件，再执行；复盘时保留原始理由，不事后改写。</p>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <Field label="日期"><input className={inputClass} type="date" value={draft.date} onChange={(e) => setDraft({ ...draft, date: e.target.value })} /></Field>
          <Field label="股票代码"><input className={inputClass} value={draft.code} onChange={(e) => setDraft({ ...draft, code: e.target.value })} /></Field>
          <Field label="动作"><select className={inputClass} value={draft.action} onChange={(e) => setDraft({ ...draft, action: e.target.value as DecisionEntry["action"] })}><option>观察</option><option>买入</option><option>加仓</option><option>减仓</option><option>卖出</option><option>复盘</option></select></Field>
          <Field label="涉及金额"><input className={inputClass} type="number" value={draft.amount || ""} onChange={(e) => setDraft({ ...draft, amount: Number(e.target.value) })} /></Field>
        </div>
        <div className="mt-3 grid gap-3 lg:grid-cols-2">
          <TextField label="决策理由" value={draft.reason} onChange={(reason) => setDraft({ ...draft, reason })} placeholder="为什么现在值得观察、买入或卖出？" />
          <TextField label="支持证据" value={draft.evidence} onChange={(evidence) => setDraft({ ...draft, evidence })} placeholder="财报、公告、估值或行业数据。" />
          <TextField label="主要风险" value={draft.risks} onChange={(risks) => setDraft({ ...draft, risks })} placeholder="最可能错在哪里？" />
          <TextField label="退出/失效条件" value={draft.exitCondition} onChange={(exitCondition) => setDraft({ ...draft, exitCondition })} placeholder="哪些可观察事实会证明判断错误？" />
          <TextField label="后续复盘" value={draft.lesson} onChange={(lesson) => setDraft({ ...draft, lesson })} placeholder="决策执行后再补充结果与教训。" />
        </div>
        <button className={`${buttonClass} mt-4`} onClick={save}>保存原始决策</button>
      </Card>

      <Card>
        <h2 className="text-lg font-semibold">决策时间线</h2>
        <div className="mt-4 space-y-3">
          {state.journal.length === 0 ? <Empty>尚无记录。第一条可以先写“为什么把某只股票加入观察池”。</Empty> : state.journal.map((item) => (
            <article key={item.id} className="rounded-xl border border-slate-200 p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex items-center gap-2"><span className="rounded-full bg-slate-900 px-2.5 py-1 text-xs font-medium text-white">{item.action}</span><span className="font-semibold">{item.code}</span><span className="text-xs text-slate-400">{item.date}</span></div>
                <div className="flex items-center gap-3"><span className="text-sm font-medium tabular-nums">{item.amount ? money(item.amount) : "未涉及资金"}</span><button className={secondaryButtonClass} onClick={() => setState((current) => ({ ...current, journal: current.journal.filter((entry) => entry.id !== item.id) }))}>删除</button></div>
              </div>
              <div className="mt-4 grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-4">
                <Block label="理由" value={item.reason} />
                <Block label="证据" value={item.evidence} />
                <Block label="风险" value={item.risks} />
                <Block label="失效条件" value={item.exitCondition} />
              </div>
              {item.lesson && <div className="mt-3 rounded-lg bg-slate-50 p-3 text-sm"><span className="font-medium">复盘：</span>{item.lesson}</div>}
            </article>
          ))}
        </div>
      </Card>
    </div>
  );
}

function TextField({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (value: string) => void; placeholder: string }) {
  return <Field label={label}><textarea className={`${inputClass} min-h-24 resize-y`} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} /></Field>;
}

function Block({ label, value }: { label: string; value: string }) {
  return <div><div className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</div><div className="mt-1 whitespace-pre-wrap text-slate-700">{value || "—"}</div></div>;
}
