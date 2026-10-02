"use client";

import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { api, type FundAnalysis, type FundListing, type FundNavPoint } from "@/lib/api";
import { useLocale } from "@/lib/i18n";

const ALERT_CLASS: Record<string, string> = {
  normal: "bg-gray-50 text-gray-600",
  warning: "bg-yellow-50 text-yellow-700",
  danger: "bg-red-50 text-red-700",
};

export default function FundModule() {
  const { t } = useLocale();
  const [code, setCode] = useState("513330");
  const [funds, setFunds] = useState<FundListing[]>([]);
  const [nav, setNav] = useState<FundNavPoint[]>([]);
  const [analysis, setAnalysis] = useState<FundAnalysis | null>(null);
  const [status, setStatus] = useState("");

  function refreshFunds() {
    api.listFunds().then(setFunds).catch(() => {});
  }

  useEffect(refreshFunds, []);

  async function ingest() {
    setStatus(t("fund.ingesting"));
    try {
      const r: any = await api.ingestFund(code);
      setStatus(t("fund.ingested", { n: r.rows_upserted }));
      refreshFunds();
      await load(code);
    } catch (e) {
      setStatus(String(e));
    }
  }

  async function load(c: string) {
    setCode(c);
    setAnalysis(null);
    setNav([]);
    try {
      const [navData, analysisData] = await Promise.all([api.getFundNav(c), api.getFundAnalysis(c)]);
      setNav(navData);
      setAnalysis(analysisData);
    } catch (e) {
      setStatus(String(e));
    }
  }

  const chartData = nav.map((p) => ({ date: p.date, value: p.close ?? p.nav ?? null }));

  return (
    <main className="max-w-5xl mx-auto p-10">
      <h1 className="text-2xl font-medium">{t("fund.title")}</h1>
      <p className="text-sm text-gray-500 mt-1">{t("fund.desc")}</p>

      <div className="mt-6 flex gap-2 items-end">
        <label className="text-sm">
          {t("fund.codeLabel")}
          <input className="border rounded px-2 py-1 block" value={code} onChange={(e) => setCode(e.target.value)} />
        </label>
        <button className="border rounded px-3 py-1 bg-black text-white" onClick={ingest}>
          {t("fund.ingest")}
        </button>
        <button className="border rounded px-3 py-1" onClick={() => load(code)}>
          {t("fund.load")}
        </button>
      </div>

      {status && <p className="mt-3 text-sm text-gray-600">{status}</p>}

      {funds.length > 0 && (
        <div className="mt-6 flex flex-wrap gap-2">
          {funds.map((f) => (
            <button
              key={f.code}
              className="border rounded px-2 py-1 text-xs text-gray-600 hover:bg-gray-50"
              onClick={() => load(f.code)}
            >
              {f.code} · {f.name} · {f.fund_type}
            </button>
          ))}
        </div>
      )}

      {analysis && (
        <>
          {analysis.premium && (
            <div className={`mt-8 rounded-lg px-4 py-3 text-sm ${ALERT_CLASS[analysis.premium.alert_level]}`}>
              <div className="font-medium">
                {t("fund.premiumRate")}: {analysis.premium.premium_rate.toFixed(2)}% ({t("fund.price")}{" "}
                {analysis.premium.price.toFixed(3)} / IOPV {analysis.premium.iopv.toFixed(3)})
              </div>
              <div className="mt-0.5">{analysis.premium.alert_message}</div>
            </div>
          )}

          <div className="mt-6 grid grid-cols-3 gap-4 text-sm">
            <Metric label={t("fund.totalReturn")} value={`${analysis.metrics.total_return.toFixed(1)}%`} />
            <Metric label={t("fund.annualizedReturn")} value={`${analysis.metrics.annualized_return.toFixed(1)}%`} />
            <Metric label={t("fund.volatility")} value={`${analysis.metrics.volatility.toFixed(1)}%`} />
            <Metric label={t("fund.sharpe")} value={analysis.metrics.sharpe_ratio.toFixed(2)} />
            <Metric label={t("fund.maxDrawdown")} value={`${analysis.metrics.max_drawdown.toFixed(1)}%`} />
            <Metric label={t("fund.winRate")} value={`${analysis.metrics.win_rate.toFixed(0)}%`} />
          </div>

          <div className="mt-8" style={{ height: 320 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={40} />
                <YAxis tick={{ fontSize: 10 }} domain={["auto", "auto"]} />
                <Tooltip />
                <Line type="monotone" dataKey="value" stroke="#2563eb" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="border rounded-lg px-3 py-2">
      <div className="text-xs text-gray-500">{label}</div>
      <div className="text-lg font-medium">{value}</div>
    </div>
  );
}
