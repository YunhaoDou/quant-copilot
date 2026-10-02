const BACKEND_URL_STORAGE_KEY = "quant-copilot-backend-url";

// Settings-page override: NEXT_PUBLIC_API_URL is baked in at build time, so a runtime
// change (e.g. pointing the desktop app at a different host) has to live in localStorage
// instead. Every fetch — including the two ad-hoc ones outside this file — reads through here.
export function getApiUrl(): string {
  if (typeof window !== "undefined") {
    const override = window.localStorage.getItem(BACKEND_URL_STORAGE_KEY);
    if (override) return override;
  }
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
}

export function setApiUrl(url: string) {
  if (typeof window !== "undefined") window.localStorage.setItem(BACKEND_URL_STORAGE_KEY, url);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${getApiUrl()}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `${res.status} ${res.statusText}`);
  }
  return res.json();
}

export type PricePoint = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type BacktestResult = {
  strategy_key: string;
  label: string;
  params: Record<string, number>;
  total_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  win_rate: number;
  num_trades: number;
  equity_curve?: Record<string, number>;
};

export type ResearchNote = {
  thesis: string;
  catalysts: string[];
  risks: string[];
  fair_value_low: number;
  fair_value_high: number;
  model: string;
  cache_hit: boolean;
  retries: number;
};

export type PaperAccount = {
  id: number;
  name: string;
  starting_cash: number;
  cash_balance: number;
};

export type PaperOrder = {
  id: number;
  symbol: string;
  side: "buy" | "sell";
  order_type: "market" | "limit" | "stop";
  quantity: number;
  limit_price: number | null;
  status: "filled" | "rejected";
  fill_price: number | null;
  reason: string | null;
  created_at: string;
};

export type PaperHolding = {
  symbol: string;
  quantity: number;
  avg_cost: number;
  last_price: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
};

export type PaperSnapshot = {
  account_id: number;
  name: string;
  cash_balance: number;
  positions_value: number;
  total_equity: number;
  starting_cash: number;
  total_return_pct: number;
  positions: PaperHolding[];
};

export type OrderInput = {
  symbol: string;
  side: "buy" | "sell";
  quantity: number;
  order_type: "market" | "limit" | "stop";
  limit_price?: number | null;
};

export type RiskAlert = {
  level: string;
  code: string;
  message: string;
};

export type RiskExposure = {
  symbol: string;
  market_value: number;
  weight_of_book: number;
  weight_of_equity: number;
};

export type RiskSnapshot = {
  account_id: number;
  name: string;
  equity: number;
  gross_exposure: number;
  net_exposure: number;
  cash: number;
  cash_pct: number;
  leverage: number;
  num_positions: number;
  hhi: number;
  effective_positions: number;
  largest_position_weight: number;
  top3_weight_of_book: number;
  drawdown: { max_drawdown: number; annualized_vol: number; window_days: number };
  exposures: RiskExposure[];
  alerts: RiskAlert[];
  thresholds: { max_position_weight: number; min_cash_pct: number; max_drawdown: number };
};

export type SimStanding = {
  account: string;
  days_logged: number;
  starting_cash: number;
  equity: number;
  total_return_pct: number;
  vs_spy_pct: number | null;
};

export type SimReport = {
  benchmark: SimStanding | null;
  strategies: SimStanding[];
};

export type SimCurve = {
  account: string;
  series: { date: string; equity: number }[];
};

export type AssetAllocation = {
  as_of_date: string;
  regime: "recovery" | "overheat" | "stagflation" | "reflation";
  growth_trend: "up" | "down";
  rate_trend: "rising" | "falling";
  spy_vs_200ma_pct: number;
  yield_10y: number;
  yield_3m: number | null;
  yield_curve_spread: number | null;
  yield_10y_change_63d: number;
  suggested_stock_pct: number;
  suggested_bond_pct: number;
  etf_recommendation: { equity: string; bond: string };
  method: string;
  disclaimer: string;
};

export type ScreeningResult = {
  symbol: string;
  as_of_date: string;
  rank: number;
  composite_score: number;
  factors: Record<string, number | null>;
  reasons: string[];
};

export type ScreeningResponse = {
  results: ScreeningResult[];
  universe_size: number;
};

export type ComplianceAnswer = {
  question: string;
  answer: string;
  citations: string[];
  grounded: boolean;
  cache_hit: boolean;
};

export type NewsHeadline = {
  title: string;
  summary: string;
  published_at: string | null;
  publisher: string;
  url: string;
  impact: "high" | "medium" | "low";
  reason: string;
};

export type NewsSentiment = {
  symbol: string;
  items: NewsHeadline[];
  overall_signal: "high" | "medium" | "low" | "quiet";
  avg_impact_score: number;
  high_impact_count: number;
  cache_hit: boolean;
};

export type FundFlowSignal = {
  symbol: string;
  as_of_date: string;
  signal: "strong_inflow" | "inflow" | "neutral" | "outflow" | "strong_outflow";
  score: number;
  cmf: number;
  mfi: number;
  obv_trend: "up" | "down" | "flat";
  large_volume_bias: number;
  window_days: number;
  method: string;
};

export type FundListing = {
  code: string;
  name: string;
  fund_type: "ETF" | "LOF" | "OTC";
  last_synced_at: string | null;
};

export type FundNavPoint = {
  date: string;
  nav: number | null;
  acc_nav: number | null;
  close: number | null;
};

export type FundAnalysis = {
  code: string;
  fund_type: "ETF" | "LOF" | "OTC";
  metrics: {
    total_return: number;
    annualized_return: number;
    volatility: number;
    sharpe_ratio: number;
    max_drawdown: number;
    win_rate: number;
    window_days: number;
  };
  premium: {
    price: number;
    iopv: number;
    premium_rate: number;
    alert_level: "normal" | "warning" | "danger";
    alert_message: string;
  } | null;
};

export const api = {
  ingestTicker: (symbol: string, name: string) =>
    request(`/tickers/${symbol}/ingest?name=${encodeURIComponent(name)}&market=CN`, { method: "POST" }),
  getPrices: (symbol: string) => request<PricePoint[]>(`/tickers/${symbol}/prices`),
  compareStrategies: (symbol: string) =>
    request<{ symbol: string; results: BacktestResult[] }>("/backtest/compare", {
      method: "POST",
      body: JSON.stringify({ symbol }),
    }),
  getResearchNote: (symbol: string, lang: string = "en") =>
    request<ResearchNote>("/research", { method: "POST", body: JSON.stringify({ symbol, lang }) }),

  // M4 paper trading
  listAccounts: () => request<PaperAccount[]>("/paper/accounts"),
  createAccount: (name: string, starting_cash: number) =>
    request<PaperAccount>("/paper/accounts", {
      method: "POST",
      body: JSON.stringify({ name, starting_cash }),
    }),
  getSnapshot: (accountId: number) => request<PaperSnapshot>(`/paper/accounts/${accountId}`),
  listOrders: (accountId: number) => request<PaperOrder[]>(`/paper/accounts/${accountId}/orders`),
  placeOrder: (accountId: number, order: OrderInput) =>
    request<PaperOrder>(`/paper/accounts/${accountId}/orders`, {
      method: "POST",
      body: JSON.stringify(order),
    }),

  // M5 risk panel
  getRisk: (accountId: number) => request<RiskSnapshot>(`/risk/accounts/${accountId}`),

  // Fund-flow signal
  getFundFlow: (symbol: string) =>
    request<FundFlowSignal>("/fundflow", { method: "POST", body: JSON.stringify({ symbol }) }),

  // A-share fund analysis
  ingestFund: (code: string) => request(`/funds/${code}/ingest`, { method: "POST" }),
  listFunds: () => request<FundListing[]>("/funds"),
  getFundNav: (code: string) => request<FundNavPoint[]>(`/funds/${code}/nav`),
  getFundAnalysis: (code: string) => request<FundAnalysis>(`/funds/${code}/analysis`),

  // News sentiment
  getNewsSentiment: (symbol: string, lang: string = "en") =>
    request<NewsSentiment>("/news", { method: "POST", body: JSON.stringify({ symbol, lang }) }),

  // Compliance Q&A
  askCompliance: (question: string, lang: string = "en") =>
    request<ComplianceAnswer>("/compliance", { method: "POST", body: JSON.stringify({ question, lang }) }),

  // Multi-factor screening
  runScreening: (topN: number = 10, lang: string = "en") =>
    request<ScreeningResponse>("/screening", { method: "POST", body: JSON.stringify({ top_n: topN, lang }) }),

  // Macro-regime asset allocation
  getAllocation: () => request<AssetAllocation>("/allocation"),

  // Sim
  getSimReport: () => request<SimReport>("/sim/report"),
  getSimCurves: () => request<SimCurve[]>("/sim/curves"),

  // Settings
  getSettings: () => request<AppSettingsView>("/settings"),
  updateSettings: (update: AppSettingsUpdate) =>
    request<AppSettingsView>("/settings", { method: "PUT", body: JSON.stringify(update) }),
};

export type AppSettingsView = {
  deepseek_api_key_set: boolean;
  deepseek_api_key_masked: string;
  news_cache_ttl_hours: number;
  llm_cache_ttl_hours: number;
};

export type AppSettingsUpdate = {
  deepseek_api_key?: string;
  news_cache_ttl_hours?: number;
  llm_cache_ttl_hours?: number;
};
