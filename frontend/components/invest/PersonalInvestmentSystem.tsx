"use client";

import { useEffect, useState } from "react";

import { INVESTMENT_VIEW_EVENT, INVESTMENT_VIEWS, InvestmentView, navigateInvestmentView, readInvestmentView } from "@/lib/invest-navigation";

import DashboardPanel from "./DashboardPanel";
import FunctionCenterPanel from "./FunctionCenterPanel";
import JournalPanel from "./JournalPanel";
import MarketRadarPanel from "./MarketRadarPanel";
import ResearchPanel from "./ResearchPanel";
import ToolsPanel from "./ToolsPanel";
import { usePersonalInvestment } from "./usePersonalInvestment";
import WatchlistPanel from "./WatchlistPanel";

export default function PersonalInvestmentSystem() {
  const [tab, setTab] = useState<InvestmentView>("dashboard");
  const { state, setState, ready, reset } = usePersonalInvestment();

  useEffect(() => {
    const sync = () => setTab(readInvestmentView());
    sync();
    window.addEventListener("popstate", sync);
    window.addEventListener(INVESTMENT_VIEW_EVENT, sync);
    return () => {
      window.removeEventListener("popstate", sync);
      window.removeEventListener(INVESTMENT_VIEW_EVENT, sync);
    };
  }, []);

  function selectTab(view: InvestmentView) {
    setTab(view);
    navigateInvestmentView(view);
  }

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
                  <span>Quant Copilot</span><span className="h-1 w-1 rounded-full bg-emerald-400" /><span>A股个人投资</span>
                </div>
                <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-[28px]">A股投资决策中心</h1>
                <p className="mt-1 max-w-2xl text-xs leading-relaxed text-emerald-50/65 sm:text-sm">先判断政策、资金与情绪，再用风险预算、企业质量和估值约束决策。</p>
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

        <nav className="mt-4 flex gap-1 overflow-x-auto rounded-2xl border border-slate-200/80 bg-white/90 p-1.5 shadow-[0_8px_30px_rgba(15,23,42,0.04)] backdrop-blur lg:hidden">
          {INVESTMENT_VIEWS.map((item) => (
            <button
              key={item.id}
              onClick={() => selectTab(item.id)}
              className={`min-w-max flex-1 rounded-xl px-4 py-2.5 text-left transition duration-200 sm:min-w-[150px] ${tab === item.id ? "bg-[#173f2c] text-white shadow-sm" : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"}`}
            >
              <div className="text-sm font-semibold">{item.shortLabel}</div>
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
          {tab === "functions" && <FunctionCenterPanel />}
        </div>

        <footer className="flex flex-wrap items-center justify-between gap-2 py-8 text-xs text-slate-400"><span>A股个人研究 · 数据保存在当前浏览器 · 不连接券商</span><span>仅用于研究与风险管理，不构成投资建议</span></footer>
      </div>
    </main>
  );
}
