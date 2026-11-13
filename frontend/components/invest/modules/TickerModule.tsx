"use client";

import { useEffect, useState } from "react";

import { api, getApiUrl, type FundFlowSignal, type NewsSentiment } from "@/lib/api";
import { useLocale } from "@/lib/i18n";
import { toSixDigit } from "@/lib/symbols";
import CompanyKline from "../CompanyKline";
import LiveQuotes from "../live-quotes";

/* ---- helpers ---- */
const FUND_FLOW_CLASS: Record<FundFlowSignal["signal"], string> = {
  strong_inflow: "bg-green-100 text-green-700",
  inflow: "bg-green-50 text-green-600",
  neutral: "bg-gray-100 text-gray-500",
  outflow: "bg-red-50 text-red-600",
  strong_outflow: "bg-red-100 text-red-700",
};

const IMPACT_STYLE: Record<string, string> = {
  high: "bg-red-100 text-red-700",
  medium: "bg-yellow-50 text-yellow-700",
  low: "bg-gray-100 text-gray-500",
};

/* ---- page ---- */
export default function TickerModule() {
  const { locale, t } = useLocale();
  const [symbol, setSymbol] = useState("600519.SS");
  const [status, setStatus] = useState("");
  const [refreshTick, setRefreshTick] = useState(0);
  const [universe, setUniverse] = useState<{ symbol: string; name: string }[]>([]);
  const [fundFlow, setFundFlow] = useState<FundFlowSignal | null>(null);
  const [fundFlowError, setFundFlowError] = useState("");
  const [news, setNews] = useState<NewsSentiment | null>(null);
  const [newsError, setNewsError] = useState("");

  // load universe list on mount
  useEffect(() => {
    fetch(`${getApiUrl()}/tickers`)
      .then((r) => r.json())
      .then((list: any[]) => setUniverse(list.filter((row) => row.market === "CN").map((row) => ({ symbol: row.symbol, name: row.asset_type==="ETF"?`${row.name} [ETF]`:row.name }))))
      .catch(() => {});
  }, []);

  // the canonical <CompanyKline> reads live candles itself; ingest only feeds the
  // stored history used by backtests/screening, so nothing here needs the old
  // /tickers/{symbol}/prices series any more.
  async function ingest() {
    const s = symbol.toUpperCase();
    setStatus(t("ticker.ingesting"));
    try {
      const r = await api.ingestTicker(s, s);
      setStatus(t("ticker.bars", { n: (r as any).rows_upserted }));
      setRefreshTick((n) => n + 1);
    } catch (e) {
      setStatus(String(e));
    }
  }

  // fund-flow signal follows the selected symbol independently of the K-line
  useEffect(() => {
    setFundFlow(null);
    setFundFlowError("");
    api
      .getFundFlow(symbol.toUpperCase())
      .then(setFundFlow)
      .catch((e) => setFundFlowError(String(e)));
  }, [symbol, refreshTick]);

  // news sentiment likewise follows the selected symbol, and re-fetches on language switch
  // (the classification "reason" text is LLM-generated, so it must be regenerated per locale)
  useEffect(() => {
    setNews(null);
    setNewsError("");
    api
      .getNewsSentiment(symbol.toUpperCase(), locale)
      .then(setNews)
      .catch((e) => setNewsError(String(e)));
  }, [symbol, locale, refreshTick]);

  const code = toSixDigit(symbol);

  return (
    <main className="max-w-5xl mx-auto px-6 py-8">
      {/* header row */}
      <div className="flex flex-wrap items-end gap-4 mb-6">
        <LiveQuotes codes={code ? [code] : []} />
        <h1 className="mt-5 text-2xl font-medium">{t("ticker.title")}</h1>
        <div className="flex gap-2 items-end">
          <label className="text-sm">
            {t("ticker.symbol")}
            <select
              className="border rounded px-2 py-1.5 block min-w-28"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
            >
              {universe.length === 0 && <option value="600519.SS">600519 · 贵州茅台</option>}
              {universe.map((u) => (
                <option key={u.symbol} value={u.symbol}>{u.symbol} · {u.name}</option>
              ))}
            </select>
          </label>
          <button className="border rounded px-3 py-1.5 bg-black text-white text-sm" onClick={ingest}>
            {t("ticker.ingest")}
          </button>
          <button className="border rounded px-3 py-1.5 text-sm" onClick={() => { setStatus(""); setRefreshTick((n) => n + 1); }}>
            {t("ticker.reload")}
          </button>
        </div>
      </div>

      {status && <p className="text-sm text-gray-500 mb-4">{status}</p>}

      {/* fund-flow signal */}
      {fundFlow && (
        <div className="border rounded-lg p-3 bg-white mb-6 flex flex-wrap items-center gap-3">
          <span className="text-xs text-gray-400">{t("ticker.fundFlow")}</span>
          <span className={`px-2 py-0.5 rounded text-xs font-medium ${FUND_FLOW_CLASS[fundFlow.signal]}`}>
            {t(`ticker.signal.${fundFlow.signal}`)}
          </span>
          <span className="text-sm font-semibold">{fundFlow.score > 0 ? "+" : ""}{fundFlow.score.toFixed(1)}</span>
          <span className="text-xs text-gray-400 ml-auto">
            CMF {fundFlow.cmf.toFixed(3)} · MFI {fundFlow.mfi.toFixed(1)} · OBV {fundFlow.obv_trend} · {fundFlow.as_of_date}
          </span>
        </div>
      )}
      {fundFlowError && <p className="text-xs text-gray-400 mb-6">{t("ticker.fundFlowError", { err: fundFlowError })}</p>}

      {/* news sentiment */}
      {news && news.items.length > 0 && (
        <div className="border rounded-lg p-3 bg-white mb-6">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs text-gray-400">{t("ticker.news")}</span>
            <span className={`px-2 py-0.5 rounded text-xs font-medium ${IMPACT_STYLE[news.overall_signal] ?? "bg-gray-100 text-gray-500"}`}>
              {t(`ticker.impact.${news.overall_signal}`)} {t("ticker.impact")}
            </span>
            {news.high_impact_count > 0 && (
              <span className="text-xs text-gray-400">{t("ticker.highImpactCount", { n: news.high_impact_count })}</span>
            )}
          </div>
          <ul className="space-y-1.5">
            {news.items.map((h, i) => (
              <li key={i} className="text-sm flex items-start gap-2">
                <span className={`shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium mt-0.5 ${IMPACT_STYLE[h.impact]}`}>
                  {t(`ticker.impact.${h.impact}`)}
                </span>
                <span>
                  <a href={h.url} target="_blank" rel="noreferrer" className="hover:underline">{h.title}</a>
                  <span className="text-gray-400"> — {h.reason}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {news && news.items.length === 0 && (
        <p className="text-xs text-gray-400 mb-6">{t("ticker.noNews")}</p>
      )}
      {newsError && <p className="text-xs text-gray-400 mb-6">{t("ticker.newsError", { err: newsError })}</p>}

      {/* canonical K-line shared with watchlist / research / market radar */}
      <div className="mt-2">
        {code
          ? <CompanyKline code={code} />
          : <p className="text-sm text-amber-800" role="alert">当前代码无法识别为六位A股代码：{symbol}</p>}
      </div>
    </main>
  );
}
