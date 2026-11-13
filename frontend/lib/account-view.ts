/**
 * Shared view model for the independent paper-account panels.
 *
 * The four strategy panels (StrategyCenterPanel, CycleStrategySimulation,
 * TrendLeaderPanel, ShiborSimulationPanel) each receive a different API payload
 * for their simulated account. Each panel maps its own payload to `AccountView`
 * (and its trades to `TradeView`) so the shared `PaperAccountCard` and
 * `TradeTable` components can render all of them identically, while
 * strategy-specific lines (SHIBOR fees/slippage, TrendLeader forward rules,
 * cycle entry price, ...) stay in the panels via the card's slots.
 */

export type AccountRules = Record<string, number>;

/** Normalized account summary consumed by `PaperAccountCard`. */
export type AccountView = {
  status: string;
  capital: number;
  cash: number;
  equity: number;
  peak: number;
  rules: AccountRules;
};

/** Loose shape accepted by `toAccountView` (each panel's own payload). */
export type PaperAccountSource = {
  status?: string | null;
  capital?: number | null;
  cash?: number | null;
  equity?: number | null;
  peak?: number | null;
  rules?: AccountRules | null;
};

/** Adapter: payload-specific account record -> shared `AccountView` (null stays null). */
export function toAccountView(source: PaperAccountSource | null | undefined): AccountView | null {
  if (!source) return null;
  return {
    status: source.status ?? "unknown",
    capital: source.capital ?? 0,
    cash: source.cash ?? 0,
    equity: source.equity ?? 0,
    peak: source.peak ?? 0,
    rules: source.rules ?? {},
  };
}

const ACCOUNT_STATUS_LABELS: Record<string, string> = {
  running: "运行中",
  paused: "已暂停",
  risk_paused: "风险暂停",
};

/** Unified Chinese status label; unknown statuses are shown verbatim. */
export function accountStatusLabel(status?: string | null): string {
  if (!status) return "尚未启动";
  return ACCOUNT_STATUS_LABELS[status] ?? status;
}

/** Status label for a normalized account (null = 尚未启动). */
export function accountStatusText(account: AccountView | null): string {
  return accountStatusLabel(account?.status);
}

/** Peak drawdown percentage, shared by every strategy account card. */
export function accountDrawdown(account: AccountView): string {
  if (!Number.isFinite(account.equity) || !Number.isFinite(account.peak) || account.peak <= 0) return "—";
  return `${((1 - account.equity / account.peak) * 100).toFixed(2)}%`;
}

/**
 * Shared suffix for the card metadata line: " · 单仓 10% · 止损 8% · 止盈 15%".
 * Kept as a suffix so panels can prefix their own strategy-specific stamp
 * (创建/启动/实际启动 ...).
 */
export function accountRulesSuffix(rules?: AccountRules | null): string {
  if (!rules) return "";
  const parts: string[] = [];
  if (rules.position_pct != null) parts.push(`单仓 ${rules.position_pct}%`);
  if (rules.sim_stop_loss_pct != null) parts.push(`止损 ${rules.sim_stop_loss_pct}%`);
  if (rules.sim_take_profit_pct != null) parts.push(`止盈 ${rules.sim_take_profit_pct}%`);
  return parts.length ? ` · ${parts.join(" · ")}` : "";
}

/** Shanghai-time stamp shared by the strategy panels (missing values stay explicit). */
export function formatAccountTime(value?: string | null): string {
  if (!value) return "尚未采集";
  return new Date(value).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" });
}

/** Normalized trade row consumed by `TradeTable`. */
export type TradeView = {
  /** Already formatted display time (panels may pass a raw ISO string). */
  time: string;
  symbol: string;
  name?: string;
  side: string;
  price: number;
  quantity: number;
  pnl?: number | null;
  fee?: number;
  reason?: string;
  /** Extra qualifier under the reason cell (e.g. StrategyCenter universe scope). */
  note?: string;
};

export function tradeSideLabel(side: string): string {
  return side === "buy" ? "买入" : "卖出";
}
