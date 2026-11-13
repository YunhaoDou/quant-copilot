"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";

import {
  INVESTMENT_VIEW_EVENT,
  INVESTMENT_VIEWS,
  type InvestmentView,
  type ViewTarget,
  canonicalizeSearch,
  navigateInvestmentView,
  resolveRoute,
} from "@/lib/invest-navigation";

import LiveQuotes from "./live-quotes";
import WorkspaceTabs from "./WorkspaceTabs";
import { usePersonalInvestment } from "./usePersonalInvestment";
import { fetchCompanyInfo } from "@/lib/company-data";
import { upsertCompany } from "@/lib/company-store";
import { Card } from "./ui";

const loading = () => (
  <Card>
    <p className="py-10 text-center text-sm text-slate-400">正在载入…</p>
  </Card>
);
const DashboardPanel = dynamic(() => import("./DashboardPanel"), { loading });
const GuidePanel = dynamic(() => import("./GuidePanel"), { loading });
const JournalPanel = dynamic(() => import("./JournalPanel"), { loading });
const MarketRadarPanel = dynamic(() => import("./MarketRadarPanel"), { loading });
const ResearchPanel = dynamic(() => import("./ResearchPanel"), { loading });
const StrategyCenterPanel = dynamic(() => import("./StrategyCenterPanel"), { loading });
const ToolsPanel = dynamic(() => import("./ToolsPanel"), { loading });
const WatchlistPanel = dynamic(() => import("./WatchlistPanel"), { loading });
const CyclePanel = dynamic(() => import("./cycle-panel"), { loading });
const DividendPanel = dynamic(() => import("./dividend-panel"), { loading });
const TickerModule = dynamic(() => import("./modules/TickerModule"), { loading });
const ScreeningModule = dynamic(() => import("./modules/ScreeningModule"), { loading });
const FundModule = dynamic(() => import("./modules/FundModule"), { loading });
const BacktestModule = dynamic(() => import("./modules/BacktestModule"), { loading });
const PaperModule = dynamic(() => import("./modules/PaperModule"), { loading });
const ComplianceModule = dynamic(() => import("./modules/ComplianceModule"), { loading });
const SettingsModule = dynamic(() => import("./modules/SettingsModule"), { loading });
const ResearchLabModule = dynamic(() => import("./modules/ResearchLabModule"), { loading });

export default function PersonalInvestmentSystem() {
  const [routeReady,setRouteReady] = useState(false);
  const [view, setView] = useState<InvestmentView>("decision");
  const [subTab, setSubTab] = useState<string>("dashboard");
  const [embedded, setEmbedded] = useState(false);
  const [guideLesson, setGuideLesson] = useState<string | null>(null);
  const [strategyId, setStrategyId] = useState<string | null>(null);
  const [guidePage, setGuidePage] = useState<string | null>(null);
  const { state, setState, ready, reset } = usePersonalInvestment();

  useEffect(() => {
    const sync = () => {
      const params = new URLSearchParams(window.location.search);
      const resolved = resolveRoute(params);
      setView(resolved.view);
      setRouteReady(true);
      setSubTab(resolved.tab);
      setEmbedded(params.get("embed") === "1");
      setGuideLesson(params.get("lesson"));
      setStrategyId(params.get("strategy"));
      setGuidePage(params.get("page") ?? (window.location.hash.slice(1) || null));
      // 旧链接（view=dashboard / functions&tool=... 等）在地址栏就地规范化为 view + tab，不新增历史记录。
      const canonical = canonicalizeSearch(params);
      if (canonical.toString() !== params.toString()) {
        const url = new URL(window.location.href);
        url.search = canonical.toString();
        window.history.replaceState({ view: resolved.view }, "", url);
        // 让已挂载的子页签（WorkspaceTabs）重新读取规范化后的 tab 参数
        window.dispatchEvent(new CustomEvent(INVESTMENT_VIEW_EVENT, { detail: resolved.view }));
      }
    };
    sync();
    window.addEventListener("popstate", sync);
    window.addEventListener(INVESTMENT_VIEW_EVENT, sync);
    return () => {
      window.removeEventListener("popstate", sync);
      window.removeEventListener(INVESTMENT_VIEW_EVENT, sync);
    };
  }, []);

  function selectView(target: ViewTarget, tab?: string) {
    navigateInvestmentView(target, undefined, tab ? { tab } : {});
    window.scrollTo(0, 0);
  }

  if (!ready || !routeReady) {
    return <div className="mx-auto max-w-7xl px-6 py-16 text-sm text-slate-500">正在载入个人投资系统…</div>;
  }

  if (embedded && view === "research" && subTab === "dividends") {
    return (
      <main className="bg-[#f4f6f2] p-4">
        <style>{"body { padding: 0 !important; }"}</style>
        <DividendPanel state={state} setState={setState} />
      </main>
    );
  }

  const showLiveQuotes = view !== "market" && view !== "help";

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
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 shadow-[0_0_0_3px_rgba(52,211,153,0.12)]" />个人档案自动保存
              </span>
              <button
                className="rounded-lg border border-white/15 px-3 py-2 text-xs text-white/70 transition duration-200 hover:border-white/25 hover:bg-white/10 hover:text-white"
                onClick={() => { if (window.confirm("确认重置当前浏览器内的驾驶舱、公司档案和决策复盘？情绪周期的人工确认与后端档案需分别管理。")) reset(); }}
              >恢复默认</button>
            </div>
          </div>
        </header>

        <nav className="mt-4 flex gap-1 overflow-x-auto rounded-2xl border border-slate-200/80 bg-white/90 p-1.5 shadow-[0_8px_30px_rgba(15,23,42,0.04)] backdrop-blur lg:hidden">
          {INVESTMENT_VIEWS.map((item) => (
            <button
              key={item.id}
              onClick={() => selectView(item.id)}
              className={`min-w-max flex-1 rounded-xl px-4 py-2.5 text-left transition duration-200 sm:min-w-[150px] ${view === item.id ? "bg-[#173f2c] text-white shadow-sm" : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"}`}
            >
              <div className="text-sm font-semibold">{item.shortLabel}</div>
            </button>
          ))}
        </nav>

        <div className="mt-5">
          {showLiveQuotes && <div className="mb-5"><LiveQuotes /></div>}

          {view === "decision" && (
            <WorkspaceTabs label="决策台" param="tab" tabs={[
              { id: "dashboard", label: "驾驶舱", content: <DashboardPanel state={state} setState={setState} /> },
              { id: "journal", label: "决策复盘", content: <JournalPanel state={state} setState={setState} /> },
            ]} />
          )}

          {view === "market" && (
            <WorkspaceTabs label="市场" param="tab" tabs={[
              { id: "radar", label: "市场雷达", content: <MarketRadarPanel state={state} setState={setState} /> },
              {
                id: "cycle",
                label: "情绪周期",
                content: (
                  <CyclePanel onResearch={async (code) => {
                    const info = await fetchCompanyInfo(code);
                    setState(current => upsertCompany(upsertCompany(current, info, "watch", "情绪周期"), info, "research"));
                    navigateInvestmentView("research", code);
                  }} />
                ),
              },
            ]} />
          )}

          {view === "research" && (
            <WorkspaceTabs label="研究" param="tab" tabs={[
              { id: "dividends", label: "红利扫描", content: <DividendPanel state={state} setState={setState} /> },
              { id: "watchlist", label: "观察池", content: <WatchlistPanel state={state} setState={setState} /> },
              { id: "research", label: "个股研究", content: <ResearchPanel state={state} setState={setState} /> },
            ]} />
          )}

          {view === "trade" && (
            <WorkspaceTabs label="交易与模拟" param="tab" tabs={[
              { id: "strategies", label: "策略研究", content: <StrategyCenterPanel strategyId={strategyId} /> },
              { id: "tools", label: "模拟工具", content: <ToolsPanel profile={state.profile} /> },
              { id: "backtest", label: "历史回测", content: <BacktestModule /> },
              { id: "paper", label: "手动模拟", content: <PaperModule /> },
              { id: "archive", label: "分析档案", content: <ResearchLabModule section="分析档案" /> },
            ]} />
          )}

          {view === "data" && (
            <WorkspaceTabs label="数据与工具" param="tab" tabs={[
              { id: "ticker", label: "股票与ETF行情", content: <TickerModule /> },
              { id: "screening", label: "多因子选股", content: <ScreeningModule /> },
              { id: "fund", label: "基金与ETF", content: <FundModule /> },
            ]} />
          )}

          {view === "help" && (
            <WorkspaceTabs label="指南与设置" param="tab" tabs={[
              {
                id: "guide",
                label: "新手指南",
                content: (
                  <GuidePanel
                    lesson={guideLesson}
                    page={guidePage}
                    onNavigate={(target, tab) => selectView(target, tab)}
                  />
                ),
              },
              { id: "settings", label: "系统设置", content: <SettingsModule /> },
              { id: "compliance", label: "旧合规问答", content: <ComplianceModule /> },
            ]} />
          )}
        </div>

        <footer className="flex flex-wrap items-center justify-between gap-2 py-8 text-xs text-slate-500"><span>A股个人研究 · 个人档案保存在当前浏览器</span><span>仅用于研究与风险管理，不构成投资建议</span></footer>
      </div>
    </main>
  );
}
