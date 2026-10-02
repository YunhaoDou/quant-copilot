"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { api, getApiUrl, type FundFlowSignal, type NewsSentiment, type PricePoint } from "@/lib/api";
import { useLocale } from "@/lib/i18n";

/* ---- helpers ---- */
const money = (n: number) => n.toLocaleString("zh-CN", { style: "currency", currency: "CNY", maximumFractionDigits: 2 });
const compact = (n: number) => (n >= 1e8 ? `${(n / 1e8).toFixed(1)}亿` : n >= 1e4 ? `${(n / 1e4).toFixed(1)}万` : String(n));
const pnl = (n: number) => (n > 0 ? "text-green-600" : n < 0 ? "text-red-600" : "text-gray-500");
const pct = (n: number) => `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;

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

/* ---- candlestick custom bar shape ---- */
function CandlestickShape(props: any) {
  const { x, y, width, height, payload } = props;
  if (!payload) return null;
  const { open, close, high, low } = payload;
  const isUp = close >= open;
  const color = isUp ? "#16a34a" : "#dc2626";
  const bodyTop = isUp ? close : open;
  const bodyBot = isUp ? open : close;
  const scale = height / (high - low || 1);
  const barW = Math.max(1, width * 0.5);
  const cx = x + width / 2;
  return (
    <g>
      <line x1={cx} x2={cx} y1={y + (high - high) * scale} y2={y + (high - low) * scale} stroke={color} strokeWidth={1} />
      <rect
        x={cx - barW / 2}
        y={y + (high - bodyTop) * scale}
        width={barW}
        height={Math.max(1, (bodyTop - bodyBot) * scale)}
        fill={color}
      />
    </g>
  );
}

/* ---- date-range filter ---- */
type Range = { label: string; days: number };
const RANGES: Range[] = [
  { label: "1M", days: 21 },
  { label: "3M", days: 63 },
  { label: "6M", days: 126 },
  { label: "1Y", days: 252 },
  { label: "ALL", days: 0 },
];

/* ---- page ---- */
export default function TickerModule() {
  const { locale, t } = useLocale();
  const [symbol, setSymbol] = useState("600519.SS");
  const [prices, setPrices] = useState<PricePoint[]>([]);
  const [status, setStatus] = useState("");
  const [range, setRange] = useState<Range>(RANGES[3]); // 1Y default
  const [universe, setUniverse] = useState<{ symbol: string; name: string }[]>([]);
  const [fundFlow, setFundFlow] = useState<FundFlowSignal | null>(null);
  const [fundFlowError, setFundFlowError] = useState("");
  const [news, setNews] = useState<NewsSentiment | null>(null);
  const [newsError, setNewsError] = useState("");

  // load universe list on mount
  useEffect(() => {
    fetch(`${getApiUrl()}/tickers`)
      .then((r) => r.json())
      .then((list: any[]) => setUniverse(list.filter((row) => row.market === "CN").map((row) => ({ symbol: row.symbol, name: row.name }))))
      .catch(() => {});
  }, []);

  async function load(sym?: string) {
    const s = (sym ?? symbol).toUpperCase();
    setStatus(t("ticker.loading"));
    try {
      const data = await api.getPrices(s);
      setPrices(data);
      setStatus(t("ticker.bars", { n: data.length }));
    } catch (e) {
      setStatus(String(e));
      setPrices([]);
    }
  }

  async function ingest() {
    const s = symbol.toUpperCase();
    setStatus(t("ticker.ingesting"));
    try {
      const r = await api.ingestTicker(s, s);
      setStatus(`${t("ticker.bars", { n: (r as any).rows_upserted })} — ${t("ticker.loading")}`);
      await load(s);
    } catch (e) {
      setStatus(String(e));
    }
  }

  // auto-load on symbol / range change
  useEffect(() => { load(); }, [symbol]);

  // fund-flow signal follows the selected symbol independently of the price load
  useEffect(() => {
    setFundFlow(null);
    setFundFlowError("");
    api
      .getFundFlow(symbol.toUpperCase())
      .then(setFundFlow)
      .catch((e) => setFundFlowError(String(e)));
  }, [symbol]);

  // news sentiment likewise follows the selected symbol, and re-fetches on language switch
  // (the classification "reason" text is LLM-generated, so it must be regenerated per locale)
  useEffect(() => {
    setNews(null);
    setNewsError("");
    api
      .getNewsSentiment(symbol.toUpperCase(), locale)
      .then(setNews)
      .catch((e) => setNewsError(String(e)));
  }, [symbol, locale]);

  const filtered = useMemo(() => {
    if (range.days === 0 || prices.length === 0) return prices;
    return prices.slice(-range.days);
  }, [prices, range]);

  // stats from the visible window
  const stats = useMemo(() => {
    if (filtered.length === 0) return null;
    const last = filtered[filtered.length - 1];
    const prev = filtered[0];
    const change = last.close - prev.close;
    const changePct = prev.close ? (change / prev.close) * 100 : 0;
    const hi = Math.max(...filtered.map((p) => p.high));
    const lo = Math.min(...filtered.map((p) => p.low));
    const totalVol = filtered.reduce((s, p) => s + p.volume, 0);
    return { last, change, changePct, hi, lo, totalVol };
  }, [filtered]);

  return (
    <main className="max-w-5xl mx-auto px-6 py-8">
      {/* header row */}
      <div className="flex flex-wrap items-end gap-4 mb-6">
        <h1 className="text-2xl font-medium">{t("ticker.title")}</h1>
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
          <button className="border rounded px-3 py-1.5 text-sm" onClick={() => load()}>
            {t("ticker.reload")}
          </button>
        </div>
        <div className="ml-auto flex gap-1">
          {RANGES.map((r) => (
            <button
              key={r.label}
              className={`px-2.5 py-1 rounded text-xs ${range.label === r.label ? "bg-gray-200 font-medium" : "text-gray-500 hover:bg-gray-100"}`}
              onClick={() => setRange(r)}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {status && <p className="text-sm text-gray-500 mb-4">{status}</p>}

      {/* stats cards */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-6">
          <Stat label={t("ticker.last")} value={money(stats.last.close)} />
          <Stat label={t("ticker.change")} value={`${pct(stats.changePct)}`} className={pnl(stats.changePct)} />
          <Stat label={t("ticker.high")} value={money(stats.hi)} />
          <Stat label={t("ticker.low")} value={money(stats.lo)} />
          <Stat label={t("ticker.volume")} value={compact(stats.totalVol)} />
        </div>
      )}

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

      {/* candlestick chart */}
      {filtered.length > 0 && (
        <div className="mb-2" style={{ height: 380 }}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={filtered}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={50} />
              <YAxis domain={["auto", "auto"]} tick={{ fontSize: 10 }} />
              <Tooltip
                formatter={(v: number) => money(v)}
                labelStyle={{ fontSize: 12 }}
              />
              <Bar dataKey="high" shape={<CandlestickShape />} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* volume subchart */}
      {filtered.length > 0 && (
        <div style={{ height: 100 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={filtered}>
              <XAxis dataKey="date" tick={false} />
              <YAxis tick={false} axisLine={false} />
              <Tooltip formatter={(v: number) => compact(v)} />
              <Bar dataKey="volume" isAnimationActive={false} radius={[1, 1, 0, 0]}>
                {filtered.map((p, i) => (
                  <Cell key={i} fill={p.close >= p.open ? "#16a34a44" : "#dc262644"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </main>
  );
}

function Stat({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div className="border rounded-lg p-3 bg-white">
      <div className="text-xs text-gray-400">{label}</div>
      <div className={`text-base font-semibold mt-0.5 ${className ?? ""}`}>{value}</div>
    </div>
  );
}
