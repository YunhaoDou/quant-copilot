"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";

import { getApiUrl } from "@/lib/api";
import { Card } from "./ui";

const loading = () => <div className="py-16 text-center text-sm text-slate-400">正在载入功能…</div>;
const TickerModule = dynamic(() => import("./modules/TickerModule"), { loading });
const ScreeningModule = dynamic(() => import("./modules/ScreeningModule"), { loading });
const FundModule = dynamic(() => import("./modules/FundModule"), { loading });
const BacktestModule = dynamic(() => import("./modules/BacktestModule"), { loading });
const AiResearchModule = dynamic(() => import("./modules/AiResearchModule"), { loading });
const PaperModule = dynamic(() => import("./modules/PaperModule"), { loading });
const SimulationModule = dynamic(() => import("./modules/SimulationModule"), { loading });
const AllocationModule = dynamic(() => import("./modules/AllocationModule"), { loading });
const ComplianceModule = dynamic(() => import("./modules/ComplianceModule"), { loading });
const SettingsModule = dynamic(() => import("./modules/SettingsModule"), { loading });

type ToolId = "ticker" | "screening" | "fund" | "backtest" | "research" | "paper" | "sim" | "allocation" | "compliance" | "settings";

const TOOLS: { id: ToolId; label: string; description: string; group: string; legacy?: boolean }[] = [
  { id: "ticker", label: "A股行情", description: "K线、成交量、资金流与新闻", group: "数据" },
  { id: "screening", label: "多因子选股", description: "动量、趋势、回撤与资金评分", group: "数据" },
  { id: "fund", label: "基金与ETF", description: "净值、折溢价、收益和风险", group: "数据" },
  { id: "backtest", label: "策略回测", description: "四类策略的收益与回撤比较", group: "研究" },
  { id: "research", label: "AI研究", description: "投资逻辑、催化剂、风险与估值", group: "研究" },
  { id: "paper", label: "模拟交易", description: "模拟账户、订单、持仓和风控", group: "执行" },
  { id: "settings", label: "系统设置", description: "模型密钥、后端地址与缓存", group: "系统" },
  { id: "sim", label: "旧策略模拟", description: "原SPY基准策略实验结果", group: "待A股化", legacy: true },
  { id: "allocation", label: "旧宏观配置", description: "原美国市场股债配置模型", group: "待A股化", legacy: true },
  { id: "compliance", label: "旧合规问答", description: "原美国交易规则知识库", group: "待A股化", legacy: true },
];

const MODULES: Record<ToolId, React.ComponentType> = {
  ticker: TickerModule,
  screening: ScreeningModule,
  fund: FundModule,
  backtest: BacktestModule,
  research: AiResearchModule,
  paper: PaperModule,
  sim: SimulationModule,
  allocation: AllocationModule,
  compliance: ComplianceModule,
  settings: SettingsModule,
};

export default function FunctionCenterPanel() {
  const [active, setActive] = useState<ToolId>("ticker");
  const [backendHealth, setBackendHealth] = useState<"loading" | "healthy" | "unavailable">("loading");
  const selected = TOOLS.find((tool) => tool.id === active) ?? TOOLS[0];
  const ActiveModule = MODULES[active];

  useEffect(() => {
    fetch(`${getApiUrl()}/health`)
      .then((response) => response.ok ? response.json() : Promise.reject())
      .then((health) => setBackendHealth(health?.components?.database?.ok ? "healthy" : "unavailable"))
      .catch(() => setBackendHealth("unavailable"));
  }, []);

  return (
    <div className="space-y-5">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-700">统一功能中心</p>
            <h2 className="mt-2 text-xl font-semibold tracking-tight text-slate-950">所有研究工具都在个人投资系统内</h2>
            <p className="mt-1 text-sm text-slate-500">优先使用A股行情、选股、基金、回测、研究和模拟交易；旧美国市场模块仅为迁移期间保留。</p>
          </div>
          <span className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs ${backendHealth === "healthy" ? "bg-emerald-50 text-emerald-700" : backendHealth === "unavailable" ? "bg-red-50 text-red-700" : "bg-slate-100 text-slate-500"}`}>
            <i className={`h-2 w-2 rounded-full ${backendHealth === "healthy" ? "bg-emerald-500" : backendHealth === "unavailable" ? "bg-red-500" : "bg-slate-400"}`} />
            后端{backendHealth === "healthy" ? "正常" : backendHealth === "unavailable" ? "不可用" : "检查中"}
          </span>
        </div>
        <div className="mt-5 grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {TOOLS.map((tool) => (
            <button
              key={tool.id}
              onClick={() => setActive(tool.id)}
              className={`rounded-2xl border p-3 text-left transition ${active === tool.id ? "border-emerald-700 bg-emerald-50 shadow-sm" : "border-slate-200 bg-white hover:border-slate-300"}`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className={`text-sm font-semibold ${active === tool.id ? "text-emerald-900" : "text-slate-800"}`}>{tool.label}</span>
                {tool.legacy && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] text-amber-700">旧版</span>}
              </div>
              <p className="mt-1 text-xs leading-5 text-slate-400">{tool.description}</p>
            </button>
          ))}
        </div>
      </Card>

      {selected.legacy && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-800">
          此功能仍使用美国市场口径，只为保证迁移期间功能不丢失；不要把其中的SPY、美元、美国国债或PDT规则用于A股决策。
        </div>
      )}

      <Card className="overflow-hidden p-0">
        <div className="border-b border-slate-100 px-5 py-4">
          <p className="text-xs text-slate-400">{selected.group}</p>
          <h2 className="mt-0.5 text-lg font-semibold text-slate-900">{selected.label}</h2>
        </div>
        <div className="p-5 [&>main]:mx-0 [&>main]:max-w-none [&>main]:p-0">
          <ActiveModule />
        </div>
      </Card>
    </div>
  );
}
