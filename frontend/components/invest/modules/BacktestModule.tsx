"use client";

import { useEffect, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { api, getApiUrl, type BacktestResult } from "@/lib/api";
import { navigateInvestmentView } from "@/lib/invest-navigation";
import { useLocale } from "@/lib/i18n";
import LiveQuotes from "../live-quotes";

const COLORS: Record<string, string> = {
  sma_crossover: "#2563eb",
  rsi_reversion: "#16a34a",
  momentum: "#d97706",
  bollinger_reversion: "#9333ea",
  relative_trend_ashare: "#0f766e",
};

type Coverage = { id: string; name: string; backtest?: { supported: boolean; reason: string } };

export default function BacktestModule() {
  const [source,setSource]=useState("direct");
  const [busy,setBusy]=useState(false);
  const { t } = useLocale();
  const [symbol, setSymbol] = useState("600519.SS");
  const [results, setResults] = useState<BacktestResult[]>([]);
  const [status, setStatus] = useState("");
  const [coverage, setCoverage] = useState<Coverage[]>([]);

  useEffect(() => {
    fetch(`${getApiUrl()}/strategy-center/overview`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((p) => setCoverage(Array.isArray(p.strategies) ? p.strategies : []))
      .catch(() => setCoverage([]));
  }, []);

  async function runComparison() {
    setStatus(t("backtest.running"));setBusy(true);setResults([]);
    try {
      const resp = source==="archive"?await api.compareStrategies(symbol):await (async()=>{
        const r=await fetch(`${getApiUrl()}/market/strategy-lab?symbol=${encodeURIComponent(symbol)}`,{cache:"no-store"});
        const p=await r.json();if(!r.ok)throw new Error(p.detail||"历史实验失败");return p;
      })();
      setResults(resp.results);
      const mode = source==="archive" ? "已保存回测记录（入库日线：仅通用技术模板）" : "直接读取真实前复权日线，不写入归档（含 A股相对强势规则）";
      setStatus(`${t("backtest.done", { n: resp.results.length })} · ${mode}`);
    } catch (e) {
      setStatus(String(e));
    } finally {setBusy(false);}
  }

  const chartData = buildChartData(results);

  return (
    <main className="max-w-5xl mx-auto p-10">
      <LiveQuotes codes={[symbol]} />
      <p className="my-3 text-xs text-amber-700">本页是<b>历史回测</b>：直接行情模式 = 4 个通用技术模板 + A股「相对强势趋势」价量规则；归档模式 = 4 个通用技术模板（入库数据没有基准行情）。未完整还原 T+1、涨跌停排队与共用风控，不代表可成交收益，也不计入前向模拟账户业绩。</p>
      <h1 className="text-2xl font-medium">{t("backtest.title")}</h1>
      <p className="text-sm text-gray-500 mt-1">{t("backtest.desc")}</p>

      <section className="mt-6 rounded-xl border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">A股策略体系与历史回测可用性</h2>
          <button className="text-xs text-emerald-800 underline" onClick={() => navigateInvestmentView("trade", undefined, { tab: "strategies" })}>去「交易与模拟 → 策略研究」看前向模拟</button>
        </div>
        <p className="mt-2 text-xs leading-6 text-slate-500">只有纯价量规则能诚实回测；依赖历史财务/分红/事件/成分/利率快照的策略只做前向模拟，避免用今天的基本面回测昨天的价格（前视偏差）。</p>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-xs">
            <thead className="border-b text-slate-400"><tr><th className="py-2">策略</th><th>历史回测</th><th>说明</th></tr></thead>
            <tbody>
              {coverage.map((item) => (
                <tr key={item.id} className="border-b border-slate-100">
                  <td className="py-2 font-medium">{item.name}</td>
                  <td className={item.backtest?.supported ? "text-emerald-700" : "text-slate-400"}>{item.backtest?.supported ? "可回测（本页）" : "仅前向模拟"}</td>
                  <td className="py-2 leading-5 text-slate-500">{item.backtest?.reason ?? "尚未声明回测覆盖范围。"}</td>
                </tr>
              ))}
              {!coverage.length && <tr><td className="py-2 text-slate-400" colSpan={3}>正在读取策略回测覆盖范围…</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <div className="mt-6 flex flex-wrap gap-2 items-end">
        <label className="text-sm">数据读取方式<select aria-label="回测数据读取方式" disabled={busy} className="border rounded px-2 py-1 block" value={source} onChange={e=>{setSource(e.target.value);setResults([]);setStatus("");}}><option value="direct">直接读取行情（近640根可得日线）</option><option value="archive">入库日线与回测归档</option></select></label>
        <label className="text-sm">
          {t("backtest.symbolLabel")}
          <input className="border rounded px-2 py-1 block" value={symbol} onChange={(e) => setSymbol(e.target.value)} />
        </label>
        <button disabled={busy} className="border rounded px-3 py-1 bg-black text-white" onClick={runComparison}>
          {t("backtest.run")}
        </button>
      </div>

      {status && <p className="mt-3 text-sm text-gray-600">{status}</p>}

      {results.length > 0 && (
        <>
          <table className="mt-8 w-full text-sm border-collapse">
            <thead>
              <tr className="text-left border-b">
                <th className="py-1">{t("backtest.strategy")}</th>
                <th>{t("backtest.totalReturn")}</th>
                <th>{t("backtest.sharpe")}</th>
                <th>{t("backtest.maxDrawdown")}</th>
                <th>{t("backtest.winRate")}</th>
                <th>{t("backtest.trades")}</th>
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
