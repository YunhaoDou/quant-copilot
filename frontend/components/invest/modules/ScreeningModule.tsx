"use client";

import { useState } from "react";

import { api, type ScreeningResponse } from "@/lib/api";
import { useLocale } from "@/lib/i18n";

const pct = (n: number | null) => (n === null ? "—" : `${(n * 100).toFixed(1)}%`);
const num = (n: number | null, digits = 2) => (n === null ? "—" : n.toFixed(digits));

export default function ScreeningModule() {
  const { locale, t } = useLocale();
  const [data, setData] = useState<ScreeningResponse | null>(null);
  const [status, setStatus] = useState("");

  async function run() {
    setStatus(t("screening.running"));
    setData(null);
    try {
      const r = await api.runScreening(10, locale);
      setData(r);
      setStatus(t("screening.scored", { n: r.universe_size }));
    } catch (e) {
      setStatus(String(e));
    }
  }

  return (
    <main className="max-w-4xl mx-auto p-10">
      <h1 className="text-2xl font-medium">{t("screening.title")}</h1>
      <p className="text-sm text-gray-500 mt-1">{t("screening.desc")}</p>

      <button className="mt-6 border rounded px-3 py-1.5 bg-black text-white text-sm" onClick={run}>
        {t("screening.run")}
      </button>
      {status && <p className="mt-3 text-sm text-gray-600">{status}</p>}

      {data && data.results.length > 0 && (
        <div className="mt-6 overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="text-left text-gray-400 border-b">
                <th className="py-2 pr-3">#</th>
                <th className="py-2 pr-3">{t("screening.symbol")}</th>
                <th className="py-2 pr-3">{t("screening.score")}</th>
                <th className="py-2 pr-3">{t("screening.mom3m")}</th>
                <th className="py-2 pr-3">{t("screening.mom12m")}</th>
                <th className="py-2 pr-3">{t("screening.fundFlow")}</th>
                <th className="py-2 pr-3">{t("screening.why")}</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((r) => (
                <tr key={r.symbol} className="border-b last:border-0">
                  <td className="py-2 pr-3 text-gray-400">{r.rank}</td>
                  <td className="py-2 pr-3 font-medium">{r.symbol}</td>
                  <td className="py-2 pr-3">{num(r.composite_score)}</td>
                  <td className="py-2 pr-3">{pct(r.factors.momentum_3m)}</td>
                  <td className="py-2 pr-3">{pct(r.factors.momentum_12m)}</td>
                  <td className="py-2 pr-3">{num(r.factors.fund_flow_score, 1)}</td>
                  <td className="py-2 pr-3 text-gray-500">{r.reasons.join(", ") || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data && data.results.length === 0 && (
        <p className="mt-6 text-sm text-gray-500">{t("screening.empty")}</p>
      )}
    </main>
  );
}
