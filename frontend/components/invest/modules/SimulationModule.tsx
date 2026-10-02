"use client";

import { useCallback, useEffect, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { api, type SimCurve, type SimReport } from "@/lib/api";
import { useLocale } from "@/lib/i18n";

const STRATEGY_COLORS: Record<string, string> = {
  "sim-sma_crossover": "#2563eb",
  "sim-rsi_reversion": "#16a34a",
  "sim-momentum": "#d97706",
  "sim-bollinger_reversion": "#9333ea",
  "sim-benchmark-spy": "#6b7280",
};

const STRATEGY_KEYS: Record<string, string> = {
  "sim-sma_crossover": "common.strategy.sma",
  "sim-rsi_reversion": "common.strategy.rsi",
  "sim-momentum": "common.strategy.momentum",
  "sim-bollinger_reversion": "common.strategy.bollinger",
  "sim-benchmark-spy": "common.strategy.spy",
};

const pnlColor = (n: number) => (n > 0 ? "text-green-600" : n < 0 ? "text-red-600" : "text-gray-500");
const pct = (n: number) => `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;

export default function SimulationModule() {
  const { t } = useLocale();
  const labelOf = useCallback((account: string) => (STRATEGY_KEYS[account] ? t(STRATEGY_KEYS[account]) : account), [t]);
  const [report, setReport] = useState<SimReport | null>(null);
  const [curves, setCurves] = useState<SimCurve[]>([]);
  const [status, setStatus] = useState("");

  const load = useCallback(async () => {
    try {
      const [r, c] = await Promise.all([api.getSimReport(), api.getSimCurves()]);
      setReport(r);
      setCurves(c);
    } catch (e) {
      setStatus(String(e));
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 120_000); // auto-refresh every 2 min
    return () => clearInterval(t);
  }, [load]);

  // Merge equity series into one [{date, sma, rsi, momentum, bollinger, spy}, ...]
  const allDates = new Set<string>();
  for (const c of curves) {
    for (const pt of c.series) allDates.add(pt.date);
  }
  const merged = [...allDates].sort().map((d) => {
    const row: Record<string, string | number> = { date: d };
    for (const c of curves) {
      const pt = c.series.find((p) => p.date === d);
      if (pt != null) row[c.account] = pt.equity;
    }
    return row;
  });

  const bench = report?.benchmark;

  return (
    <main className="max-w-5xl mx-auto p-10">
      <h1 className="text-2xl font-medium">{t("sim.title")}</h1>
      <p className="text-sm text-gray-500 mt-1">
        {t("sim.desc")}
        <span className="ml-2">
          <button className="underline text-blue-600" onClick={load}>
            {t("sim.refreshNow")}
          </button>
        </span>
      </p>

      {status && <p className="text-sm text-red-600 mt-2">{status}</p>}

      {/* Standings */}
      {report && (
        <section className="mt-8">
          <h2 className="text-lg font-medium">{t("sim.standings")}</h2>
          <table className="mt-3 w-full text-sm border-collapse">
            <thead>
              <tr className="text-left border-b font-medium">
                <th className="py-2">{t("sim.account")}</th>
                <th>{t("sim.equity")}</th>
                <th>{t("sim.return")}</th>
                <th>{t("sim.vsSpy")}</th>
                <th>{t("sim.days")}</th>
              </tr>
            </thead>
            <tbody>
              {bench && (
                <tr className="border-b bg-gray-50">
                  <td className="py-2 font-medium text-gray-500">{labelOf(bench.account)}</td>
                  <td>${bench.equity.toLocaleString()}</td>
                  <td className={pnlColor(bench.total_return_pct)}>{pct(bench.total_return_pct)}</td>
                  <td className="text-gray-400">—</td>
                  <td className="text-gray-500">{bench.days_logged}</td>
                </tr>
              )}
              {report.strategies.map((s) => (
                <tr key={s.account} className="border-b">
                  <td className="py-2 font-medium">{labelOf(s.account)}</td>
                  <td>${s.equity.toLocaleString()}</td>
                  <td className={pnlColor(s.total_return_pct)}>{pct(s.total_return_pct)}</td>
                  <td className={s.vs_spy_pct != null ? pnlColor(s.vs_spy_pct) : "text-gray-400"}>
                    {s.vs_spy_pct != null ? pct(s.vs_spy_pct) : "—"}
                  </td>
                  <td className="text-gray-500">{s.days_logged}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* Equity curve chart */}
      {merged.length > 1 && (
        <section className="mt-10">
          <h2 className="text-lg font-medium">{t("sim.equityCurves")}</h2>
          <div className="mt-3" style={{ height: 400 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={merged}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={40} />
                <YAxis tick={{ fontSize: 10 }} domain={["auto", "auto"]} />
                <Tooltip formatter={(v: number) => `$${v.toLocaleString()}`} />
                <Legend />
                {curves.map((c) => (
                  <Line
                    key={c.account}
                    type="monotone"
                    dataKey={c.account}
                    name={labelOf(c.account)}
                    stroke={STRATEGY_COLORS[c.account] ?? "#000"}
                    dot={false}
                    strokeWidth={c.account === "sim-benchmark-spy" ? 2.5 : 1.5}
                    strokeDasharray={c.account === "sim-benchmark-spy" ? "5 5" : undefined}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      <footer className="mt-10 text-xs text-gray-400">
        {t("sim.footerPre")}{" "}
        <code className="bg-gray-100 px-1">docs/sim-protocol.md</code>
        {t("sim.footerPost")}
      </footer>
    </main>
  );
}
