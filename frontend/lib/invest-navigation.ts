export type InvestmentView = "dashboard" | "market" | "cycle" | "dividends" | "watchlist" | "research" | "tools" | "journal" | "functions";

export const INVESTMENT_VIEWS: { id: InvestmentView; label: string; shortLabel: string; description: string; group: "决策" | "工具" }[] = [
  { id: "dashboard", label: "A股驾驶舱", shortLabel: "驾驶舱", description: "资产、持仓与回撤防线", group: "决策" },
  { id: "market", label: "市场雷达", shortLabel: "雷达", description: "市场事实、证据与候选", group: "决策" },
  { id: "cycle", label: "情绪周期", shortLabel: "周期", description: "主线、龙头与历史验证", group: "决策" },
  { id: "dividends", label: "红利看板", shortLabel: "红利", description: "真实分红、分类与价格位置", group: "决策" },
  { id: "watchlist", label: "A股观察池", shortLabel: "观察池", description: "估值、股息与质量", group: "决策" },
  { id: "research", label: "个股研究", shortLabel: "研究", description: "论证与失效条件", group: "决策" },
  { id: "tools", label: "模拟工具", shortLabel: "模拟", description: "仓位冲击与估值", group: "工具" },
  { id: "journal", label: "决策复盘", shortLabel: "复盘", description: "证据、退出与教训", group: "工具" },
  { id: "functions", label: "功能中心", shortLabel: "功能", description: "行情、选股与回测", group: "工具" },
];

export const INVESTMENT_VIEW_EVENT = "quant-copilot-investment-view";

export function isInvestmentView(value: string | null): value is InvestmentView {
  return INVESTMENT_VIEWS.some((item) => item.id === value);
}

export function readInvestmentView(): InvestmentView {
  if (typeof window === "undefined") return "dashboard";
  const view = new URLSearchParams(window.location.search).get("view");
  return isInvestmentView(view) ? view : "dashboard";
}

export function navigateInvestmentView(view: InvestmentView) {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  url.pathname = "/invest";
  url.searchParams.set("view", view);
  window.history.pushState({ view }, "", url);
  window.dispatchEvent(new CustomEvent(INVESTMENT_VIEW_EVENT, { detail: view }));
}
