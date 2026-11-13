export type InvestmentView = "decision" | "market" | "research" | "trade" | "data" | "help";

/** 旧版 11 视图 id。保留为别名，保证旧链接、书签和组件内链继续可用。 */
export type LegacyViewId =
  | "dashboard"
  | "cycle"
  | "dividends"
  | "watchlist"
  | "strategies"
  | "tools"
  | "journal"
  | "functions"
  | "guide";

/** 任何可以导航到的目标：新视图 id 或旧视图别名。 */
export type ViewTarget = InvestmentView | LegacyViewId;

export type InvestmentTab = { id: string; label: string };

export type InvestmentViewDef = {
  id: InvestmentView;
  label: string;
  shortLabel: string;
  description: string;
  group: "工作流" | "工具";
  tabs: InvestmentTab[];
};

/**
 * 页面即工作流：11 个旧视图按“同一件事”合并成 6 个页面，页面内用子页签保留全部功能。
 * 默认子页签 = tabs[0]；刷新、前进后退、旧链接都能回到同一位置。
 */
export const INVESTMENT_VIEWS: InvestmentViewDef[] = [
  {
    id: "decision",
    label: "决策台",
    shortLabel: "决策",
    description: "资产、持仓、回撤防线与决策复盘",
    group: "工作流",
    tabs: [
      { id: "dashboard", label: "驾驶舱" },
      { id: "journal", label: "决策复盘" },
    ],
  },
  {
    id: "market",
    label: "市场",
    shortLabel: "市场",
    description: "环境、主线、情绪周期与股债趋势",
    group: "工作流",
    tabs: [
      { id: "radar", label: "市场雷达" },
      { id: "cycle", label: "情绪周期" },
    ],
  },
  {
    id: "research",
    label: "研究",
    shortLabel: "研究",
    description: "红利扫描、观察池与个股研究",
    group: "工作流",
    tabs: [
      { id: "dividends", label: "红利扫描" },
      { id: "watchlist", label: "观察池" },
      { id: "research", label: "个股研究" },
    ],
  },
  {
    id: "trade",
    label: "交易与模拟",
    shortLabel: "交易",
    description: "八类策略、模拟工具、回测与分析档案",
    group: "工作流",
    tabs: [
      { id: "strategies", label: "策略研究" },
      { id: "tools", label: "模拟工具" },
      { id: "backtest", label: "历史回测" },
      { id: "paper", label: "手动模拟" },
      { id: "archive", label: "分析档案" },
    ],
  },
  {
    id: "data",
    label: "数据与工具",
    shortLabel: "数据",
    description: "股票与 ETF 行情、多因子选股、基金",
    group: "工具",
    tabs: [
      { id: "ticker", label: "股票与ETF行情" },
      { id: "screening", label: "多因子选股" },
      { id: "fund", label: "基金与ETF" },
    ],
  },
  {
    id: "help",
    label: "指南与设置",
    shortLabel: "设置",
    description: "新手指南、系统设置与旧合规问答",
    group: "工具",
    tabs: [
      { id: "guide", label: "新手指南" },
      { id: "settings", label: "系统设置" },
      { id: "compliance", label: "旧合规问答" },
    ],
  },
];

export const INVESTMENT_VIEW_EVENT = "quant-copilot-investment-view";

const LEGACY_VIEW_ALIASES: Record<LegacyViewId, { view: InvestmentView; tab: string }> = {
  dashboard: { view: "decision", tab: "dashboard" },
  journal: { view: "decision", tab: "journal" },
  cycle: { view: "market", tab: "cycle" },
  dividends: { view: "research", tab: "dividends" },
  watchlist: { view: "research", tab: "watchlist" },
  strategies: { view: "trade", tab: "strategies" },
  tools: { view: "trade", tab: "tools" },
  functions: { view: "data", tab: "ticker" },
  guide: { view: "help", tab: "guide" },
};

/** 旧「功能中心」的工具 id → 新工作流页位置。 */
const LEGACY_TOOL_ALIASES: Record<string, { view: InvestmentView; tab: string }> = {
  ticker: { view: "data", tab: "ticker" },
  screening: { view: "data", tab: "screening" },
  fund: { view: "data", tab: "fund" },
  backtest: { view: "trade", tab: "backtest" },
  paper: { view: "trade", tab: "paper" },
  archive: { view: "trade", tab: "archive" },
  lab: { view: "trade", tab: "archive" },
  sim: { view: "trade", tab: "backtest" },
  research: { view: "research", tab: "research" },
  allocation: { view: "market", tab: "radar" },
  settings: { view: "help", tab: "settings" },
  compliance: { view: "help", tab: "compliance" },
};

export function isInvestmentView(value: string | null | undefined): value is InvestmentView {
  return INVESTMENT_VIEWS.some((item) => item.id === value);
}

export function isLegacyViewId(value: string | null | undefined): value is LegacyViewId {
  return value != null && value in LEGACY_VIEW_ALIASES;
}

export function tabsFor(view: InvestmentView): InvestmentTab[] {
  return INVESTMENT_VIEWS.find((item) => item.id === view)?.tabs ?? [];
}

export function defaultTab(view: InvestmentView): string {
  return tabsFor(view)[0]?.id ?? "";
}

export type ResolvedRoute = { view: InvestmentView; tab: string; section: string | null };

/** 把 legacy/new 的 view、tool、tab、section 组合解析成唯一 canonical 路由。 */
export function resolveRoute(search: URLSearchParams): ResolvedRoute {
  const rawView = search.get("view");
  const rawTool = search.get("tool");
  const rawTab = search.get("tab");
  const section = search.get("section");

  let view: InvestmentView = "decision";
  let tab: string | null = null;

  if (rawView === "functions" && rawTool && LEGACY_TOOL_ALIASES[rawTool]) {
    const alias = LEGACY_TOOL_ALIASES[rawTool];
    view = alias.view;
    tab = alias.tab;
  } else if (isInvestmentView(rawView)) {
    view = rawView;
  } else if (isLegacyViewId(rawView)) {
    const alias = LEGACY_VIEW_ALIASES[rawView];
    view = alias.view;
    tab = alias.tab;
  } else if (!rawView && rawTool && LEGACY_TOOL_ALIASES[rawTool]) {
    const alias = LEGACY_TOOL_ALIASES[rawTool];
    view = alias.view;
    tab = alias.tab;
  }

  const validTabs = tabsFor(view);
  if (rawTab && validTabs.some((item) => item.id === rawTab)) tab = rawTab;
  return { view, tab: tab ?? validTabs[0]?.id ?? "", section };
}

/** 把当前 URL 里的 legacy 参数规范化，只保留 canonical view/tab，其它参数原样保留。 */
export function canonicalizeSearch(search: URLSearchParams): URLSearchParams {
  const resolved = resolveRoute(search);
  const next = new URLSearchParams(search.toString());
  next.set("view", resolved.view);
  next.set("tab", resolved.tab);
  next.delete("tool");
  return next;
}

export function readInvestmentView(): InvestmentView {
  if (typeof window === "undefined") return "decision";
  return resolveRoute(new URLSearchParams(window.location.search)).view;
}

export function readInvestmentTab(): string {
  if (typeof window === "undefined") return "dashboard";
  return resolveRoute(new URLSearchParams(window.location.search)).tab;
}

export function readInvestmentSection(): string | null {
  if (typeof window === "undefined") return null;
  return resolveRoute(new URLSearchParams(window.location.search)).section;
}

function resolveTarget(
  target: ViewTarget,
  tab?: string,
  tool?: string,
): { view: InvestmentView; tab: string } {
  if (target === "functions" && tool && LEGACY_TOOL_ALIASES[tool]) {
    const alias = LEGACY_TOOL_ALIASES[tool];
    return { view: alias.view, tab: tab ?? alias.tab };
  }
  if (isInvestmentView(target)) {
    const validTabs = tabsFor(target);
    return {
      view: target,
      tab: tab && validTabs.some((item) => item.id === tab) ? tab : defaultTab(target),
    };
  }
  const alias = LEGACY_VIEW_ALIASES[target];
  return { view: alias.view, tab: tab ?? alias.tab };
}

/** 导航到某个视图（新 id 或旧别名），可选指定子页签 / section。 */
export function navigateInvestmentView(
  target: ViewTarget,
  company?: string,
  options: { tab?: string; section?: string; strategy?: string; tool?: string } = {},
) {
  if (typeof window === "undefined") return;
  const resolved = resolveTarget(target, options.tab, options.tool);
  const url = new URL(window.location.href);
  url.pathname = "/invest";
  url.hash = "";
  url.searchParams.set("view", resolved.view);
  url.searchParams.set("tab", resolved.tab);
  url.searchParams.delete("lesson");
  url.searchParams.delete("page");
  url.searchParams.delete("tool");
  for (const key of ["section", "strategy", "fund", "cycleTab", "cycleEvent"] as const) {
    url.searchParams.delete(key);
  }
  if (options.section) url.searchParams.set("section", options.section);
  if (options.strategy) url.searchParams.set("strategy", options.strategy);
  if (company) url.searchParams.set("company", company);
  else url.searchParams.delete("company");
  window.history.pushState({ view: resolved.view }, "", url);
  window.dispatchEvent(new CustomEvent(INVESTMENT_VIEW_EVENT, { detail: resolved.view }));
}

/** 用于文案：把任意目标（含旧 id）翻译成当前页面名称。 */
export function viewTargetLabel(target: ViewTarget): string {
  const view = resolveTarget(target).view;
  return INVESTMENT_VIEWS.find((item) => item.id === view)?.label ?? "页面";
}
