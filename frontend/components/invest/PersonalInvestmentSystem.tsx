"use client";

import { useState } from "react";

import DashboardPanel from "./DashboardPanel";
import JournalPanel from "./JournalPanel";
import ResearchPanel from "./ResearchPanel";
import ToolsPanel from "./ToolsPanel";
import { usePersonalInvestment } from "./usePersonalInvestment";
import WatchlistPanel from "./WatchlistPanel";

type Tab = "dashboard" | "watchlist" | "research" | "tools" | "journal";

const TABS: { id: Tab; label: string; description: string }[] = [
  { id: "dashboard", label: "投资驾驶舱", description: "资产、持仓与20%回撤防线" },
  { id: "watchlist", label: "A股观察池", description: "估值、股息、质量与观察区间" },
  { id: "research", label: "个股研究", description: "论证、反方观点与失效条件" },
  { id: "tools", label: "模拟工具", description: "仓位冲击与估值情景" },
  { id: "journal", label: "决策复盘", description: "保存当时证据与后续教训" },
];

export default function PersonalInvestmentSystem() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const { state, setState, ready, reset } = usePersonalInvestment();

  if (!ready) {
    return <div className="mx-auto max-w-7xl px-6 py-16 text-sm text-slate-500">正在载入个人投资系统…</div>;
  }

  return (
    <main className="min-h-screen bg-[#f5f7f3]">
      <div className="mx-auto max-w-7xl px-5 py-7 lg:px-8">
        <header className="overflow-hidden rounded-3xl bg-[#10281d] px-6 py-7 text-white shadow-xl shadow-emerald-950/10 lg:px-8">
          <div className="flex flex-wrap items-end justify-between gap-5">
            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.24em] text-emerald-300">Personal Investment OS</div>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight">个人投资决策系统</h1>
              <p className="mt-2 max-w-2xl text-sm leading-relaxed text-emerald-50/75">用资产配置、仓位和失效条件约束风险；用企业质量和估值支持决策。数据仅保存在当前浏览器，不连接券商。</p>
            </div>
            <div className="flex items-center gap-3">
              <span className="rounded-full border border-emerald-300/30 bg-emerald-400/10 px-3 py-1.5 text-xs text-emerald-100">自动本地保存</span>
              <button
                className="rounded-lg border border-white/20 px-3 py-1.5 text-xs text-white/80 transition hover:bg-white/10"
                onClick={() => { if (window.confirm("确认清空所有个人投资数据并恢复默认设置？")) reset(); }}
              >恢复默认</button>
            </div>
          </div>
        </header>

        <nav className="mt-5 grid gap-2 rounded-2xl border border-slate-200 bg-white p-2 shadow-sm sm:grid-cols-2 lg:grid-cols-5">
          {TABS.map((item) => (
            <button
              key={item.id}
              onClick={() => setTab(item.id)}
              className={`rounded-xl px-4 py-3 text-left transition ${tab === item.id ? "bg-emerald-700 text-white shadow-sm" : "text-slate-600 hover:bg-slate-50"}`}
            >
              <div className="text-sm font-semibold">{item.label}</div>
              <div className={`mt-0.5 text-[11px] ${tab === item.id ? "text-emerald-100" : "text-slate-400"}`}>{item.description}</div>
            </button>
          ))}
        </nav>

        <div className="mt-5">
          {tab === "dashboard" && <DashboardPanel state={state} setState={setState} />}
          {tab === "watchlist" && <WatchlistPanel state={state} setState={setState} />}
          {tab === "research" && <ResearchPanel state={state} setState={setState} />}
          {tab === "tools" && <ToolsPanel totalAssets={state.profile.currentAssets} />}
          {tab === "journal" && <JournalPanel state={state} setState={setState} />}
        </div>

        <footer className="py-8 text-center text-xs text-slate-400">仅用于研究、记录和风险管理，不构成投资建议，不执行真实交易。</footer>
      </div>
    </main>
  );
}
