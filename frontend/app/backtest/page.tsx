"use client";

import { useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { api, type BacktestResult } from "@/lib/api";

const COLORS: Record<string, string> = {
  sma_crossover: "#2563eb",
  rsi_reversion: "#16a34a",
  momentum: "#d97706",
  bollinger_reversion: "#9333ea",
};

export default function BacktestPage() {
  const [symbol, setSymbol] = useState("600519");
  const [results, setResults] = useState<BacktestResult[]>([]);
  const [status, setStatus] = useState("");

  async function runComparison() {
    setStatus("running 4-strategy comparison against stored history...");
    try {
      const resp = await api.compareStrategies(symbol);
      setResults(resp.results);
      setStatus(`done — ${resp.results.length} strategies compared`);
    } catch (e) {
      setStatus(String(e));
    }
  }

  const chartData = buildChartData(results);

  return (
    <main className="max-w-5xl mx-auto p-10">
      <h1 className="text-2xl font-medium">4-strategy backtest comparison</h1>
      <p className="text-sm text-gray-500 mt-1">
        SMA crossover, RSI mean-reversion, time-series momentum, Bollinger reversion — run against the
        ticker&apos;s full stored history via vectorbt.
      </p>

      <div className="mt-6 flex gap-2 items-end">
        <label className="text-sm">
          Symbol (must already be ingested on the Ticker page)
          <input className="border rounded px-2 py-1 block" value={symbol} onChange={(e) => setSymbol(e.target.value)} />
        </label>
        <button className="border rounded px-3 py-1 bg-black text-white" onClick={runComparison}>
          Run comparison
        </button>
      </div>

      {status && <p className="mt-3 text-sm text-gray-600">{status}</p>}

      {results.length > 0 && (
        <>
          <table className="mt-8 w-full text-sm border-collapse">
            <thead>
              <tr className="text-left border-b">
                <th className="py-1">Strategy</th>
                <th>Total return</th>
                <th>Sharpe</th>
                <th>Max drawdown</th>
                <th>Win rate</th>
                <th>Trades</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r) => (
                <tr key={r.strategy_key} className="border-b">
                  <td className="py-1">{r.label}</td>
                  <td>{(r.total_return * 100).toFixed(1)}%</td>
                  <td>{r.sharpe_ratio.toFixed(2)}</td>
                  <td>{(r.max_drawdown * 100).toFixed(1)}%</td>
                  <td>{(r.win_rate * 100).toFixed(0)}%</td>
                  <td>{r.num_trades}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="mt-8" style={{ height: 360 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={40} />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip />
                <Legend />
                {results.map((r) => (
                  <Line
                    key={r.strategy_key}
                    type="monotone"
                    dataKey={r.strategy_key}
                    name={r.label}
                    stroke={COLORS[r.strategy_key] ?? "#000"}
                    dot={false}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </main>
  );
}

function buildChartData(results: BacktestResult[]) {
  if (results.length === 0 || !results[0].equity_curve) return [];
  const dates = Object.keys(results[0].equity_curve);
  return dates.map((date) => {
    const row: Record<string, string | number> = { date };
    for (const r of results) {
      if (r.equity_curve) row[r.strategy_key] = r.equity_curve[date];
    }
    return row;
  });
}
