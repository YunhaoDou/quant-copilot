"use client";

import { useEffect, useState } from "react";

import { api, type AssetAllocation } from "@/lib/api";
import { useLocale } from "@/lib/i18n";

const REGIME_CLASS: Record<AssetAllocation["regime"], string> = {
  recovery: "bg-green-100 text-green-700",
  overheat: "bg-yellow-50 text-yellow-700",
  stagflation: "bg-red-100 text-red-700",
  reflation: "bg-blue-50 text-blue-700",
};

export default function AllocationModule() {
  const { t } = useLocale();
  const [data, setData] = useState<AssetAllocation | null>(null);
  const [status, setStatus] = useState("");

  async function load() {
    setStatus(t("allocation.loading"));
    try {
      const r = await api.getAllocation();
      setData(r);
      setStatus("");
    } catch (e) {
      setStatus(String(e));
    }
  }

  useEffect(() => { load(); }, []);

  return (
    <main className="max-w-3xl mx-auto p-10">
      <h1 className="text-2xl font-medium">{t("allocation.title")}</h1>
      <p className="text-sm text-gray-500 mt-1">{t("allocation.desc")}</p>

      {status && <p className="mt-3 text-sm text-gray-600">{status}</p>}

      {data && (
        <div className="mt-6 space-y-6">
          <div className="flex items-center gap-3">
            <span className={`px-3 py-1 rounded text-sm font-medium ${REGIME_CLASS[data.regime]}`}>
              {t(`allocation.regime.${data.regime}`)}
            </span>
            <span className="text-sm text-gray-500">{t("allocation.asOf", { date: data.as_of_date })}</span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Stat label={t("allocation.growthTrend")} value={t(`allocation.trend.${data.growth_trend}`)} />
            <Stat label={t("allocation.rateTrend")} value={t(`allocation.trend.${data.rate_trend}`)} />
            <Stat label={t("allocation.spyVs200")} value={`${(data.spy_vs_200ma_pct * 100).toFixed(1)}%`} />
            <Stat label={t("allocation.yield10y")} value={`${data.yield_10y.toFixed(2)}%`} />
            <Stat label={t("allocation.yield3m")} value={data.yield_3m !== null ? `${data.yield_3m.toFixed(2)}%` : "—"} />
            <Stat
              label={t("allocation.yieldCurve")}
              value={data.yield_curve_spread !== null ? `${data.yield_curve_spread.toFixed(2)}pp` : "—"}
            />
            <Stat label={t("allocation.stockPct")} value={`${data.suggested_stock_pct}%`} />
            <Stat label={t("allocation.bondPct")} value={`${data.suggested_bond_pct}%`} />
          </div>

          <div className="border rounded-lg p-3 bg-white">
            <div className="text-xs text-gray-400 mb-1">{t("allocation.etfPicks")}</div>
            <div className="text-sm">
              {t("allocation.equity")}: {data.etf_recommendation.equity} · {t("allocation.bond")}: {data.etf_recommendation.bond}
            </div>
          </div>

          <p className="text-xs text-amber-600">{t("allocation.disclaimer")}</p>
        </div>
      )}
    </main>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="border rounded-lg p-3 bg-white">
      <div className="text-xs text-gray-400">{label}</div>
      <div className="text-base font-semibold mt-0.5">{value}</div>
    </div>
  );
}
