"use client";

import { useState } from "react";

import DashboardPanel from "./DashboardPanel";
import JournalPanel from "./JournalPanel";
import MarketRadarPanel from "./MarketRadarPanel";
import ResearchPanel from "./ResearchPanel";
import ToolsPanel from "./ToolsPanel";
import { usePersonalInvestment } from "./usePersonalInvestment";
import WatchlistPanel from "./WatchlistPanel";

type Tab = "dashboard" | "market" | "watchlist" | "research" | "tools" | "journal";

const TABS: { id: Tab; label: string; description: string }[] = [
  { id: "dashboard", label: "投资驾驶舱", description: "资产、持仓与20%回撤防线" },
  { id: "market", label: "A股雷达", description: "环境、仓位与主线共振" },
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
    <main className="min-h-screen bg-[#f4f6f2] text-slate-800">
      <div className="pointer-events-none fixed inset-x-0 top-0 h-72 bg-[radial-gradient(circle_at_70%_-20%,rgba(16,185,129,0.12),transparent_48%)]" />
      <div className="relative mx-auto max-w-[1440px] px-4 py-5 sm:px-6 lg:px-8 lg:py-7">
        <header className="rounded-[22px] border border-emerald-950/10 bg-[#10281d] px-5 py-5 text-white shadow-[0_18px_45px_rgba(16,40,29,0.14)] sm:px-6 lg:px-7">
          <div className="flex flex-wrap items-center justify-between gap-5">
            <div className="flex min-w-0 items-center gap-4">
              <div className="hidden h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/10 sm:flex">
                <span className="text-lg font-semibold text-emerald-200">Q</span>
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.2em] text-emerald-300/90">
                  <span>Quant Copilot</span><span className="h-1 w-1 rounded-full bg-emerald-400" /><span>个人投资</span>
                </div>
                <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-[28px]">投资决策中心</h1>
                <p className="mt-1 max-w-2xl text-xs leading-relaxed text-emerald-50/65 sm:text-sm">以风险预算约束仓位，以企业质量和估值支持长期决策。</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-2 rounded-lg border border-emerald-300/20 bg-emerald-400/10 px-3 py-2 text-xs text-emerald-50/90">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 shadow-[0_0_0_3px_rgba(52,211,153,0.12)]" />本地自动保存
              </span>
              <button
                className="rounded-lg border border-white/15 px-3 py-2 text-xs text-white/70 transition duration-200 hover:border-white/25 hover:bg-white/10 hover:text-white"
                onClick={() => { if (window.confirm("确认清空所有个人投资数据并恢复默认设置？")) reset(); }}
              >恢复默认</button>
            </div>
          </div>
        </header>

        <nav className="mt-4 flex gap-1 overflow-x-auto rounded-2xl border border-slate-200/80 bg-white/90 p-1.5 shadow-[0_8px_30px_rgba(15,23,42,0.04)] backdrop-blur">
          {TABS.map((item) => (
            <button
              key={item.id}
              onClick={() => setTab(item.id)}
              className={`min-w-max flex-1 rounded-xl px-4 py-2.5 text-left transition duration-200 sm:min-w-[150px] ${tab === item.id ? "bg-[#173f2c] text-white shadow-sm" : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"}`}
            >
              <div className="text-sm font-semibold">{item.label}</div>
              <div className={`mt-0.5 hidden text-[11px] lg:block ${tab === item.id ? "text-emerald-100/70" : "text-slate-400"}`}>{item.description}</div>
            </button>
          ))}
        </nav>

        <div className="mt-5">
          {tab === "dashboard" && <DashboardPanel state={state} setState={setState} />}
          {tab === "market" && <MarketRadarPanel state={state} setState={setState} />}
          {tab === "watchlist" && <WatchlistPanel state={state} setState={setState} />}
          {tab === "research" && <ResearchPanel state={state} setState={setState} />}
          {tab === "tools" && <ToolsPanel totalAssets={state.profile.currentAssets} />}
          {tab === "journal" && <JournalPanel state={state} setState={setState} />}
        </div>

        <footer className="flex flex-wrap items-center justify-between gap-2 py-8 text-xs text-slate-400"><span>数据保存在当前浏览器 · 不连接券商</span><span>仅用于研究与风险管理，不构成投资建议</span></footer>
      </div>
    </main>
  );
}
