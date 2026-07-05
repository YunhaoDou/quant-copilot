const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
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

export const api = {
  ingestTicker: (symbol: string, name: string) =>
    request(`/tickers/${symbol}/ingest?name=${encodeURIComponent(name)}`, { method: "POST" }),
  getPrices: (symbol: string) => request<PricePoint[]>(`/tickers/${symbol}/prices`),
  compareStrategies: (symbol: string) =>
    request<{ symbol: string; results: BacktestResult[] }>("/backtest/compare", {
      method: "POST",
      body: JSON.stringify({ symbol }),
    }),
  getResearchNote: (symbol: string) =>
    request<ResearchNote>("/research", { method: "POST", body: JSON.stringify({ symbol }) }),
};
