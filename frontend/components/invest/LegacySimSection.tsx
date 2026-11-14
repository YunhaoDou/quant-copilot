"use client";

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
const LegacySimChart=dynamic(()=>import("./LegacySimChart"),{loading:()=> <p role="status" className="py-8 text-sm text-slate-500">正在载入净值图表…</p>});

import { api, type LegacySimCurve, type LegacySimReport, type LegacySimStanding } from "@/lib/api";
import { navigateInvestmentView } from "@/lib/invest-navigation";
import { Card, secondaryButtonClass } from "./ui";

const money = (n: number) => n.toLocaleString("zh-CN", { style: "currency", currency: "CNY", maximumFractionDigits: 2 });
const pct = (n: number | null | undefined) => (n == null ? "—" : `${n > 0 ? "+" : ""}${n.toFixed(2)}%`);
const pctClass = (n: number | null | undefined) =>
  n == null ? "text-slate-400" : n > 0 ? "text-emerald-700" : n < 0 ? "text-rose-700" : "text-slate-600";

/** 遗留美股策略模拟：4 个旧 vectorbt 模板 + SPY 基准，只读展示，不改账户、不下单。 */
export default function LegacySimSection() {
  const [report, setReport] = useState<LegacySimReport | null>(null);
  const [curves, setCurves] = useState<LegacySimCurve[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [standings, equity] = await Promise.all([api.getLegacySimReport(), api.getLegacySimCurves()]);
        if (!active) return;
        setReport(standings);
        setCurves(equity);
        setError("");
      } catch (e) {
        if (active) setError(String(e));
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const rows = useMemo(() => {
    if (!report) return [] as LegacySimStanding[];
    return [...report.strategies, ...(report.benchmark ? [report.benchmark] : [])];
  }, [report]);

  const hasChartData=curves.some(curve=>curve.series.length>0);
  const curveAccounts = curves.map((curve) => curve.account);
  const chosen = selected ? rows.find((row) => row.account === selected) ?? null : null;
  const lastDate = curveAccounts.length
    ? curves.flatMap((curve) => curve.series.map((point) => point.date)).sort().at(-1)
    : null;

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold">遗留美股策略模拟（只读）</h3>
          <p className="mt-2 max-w-3xl text-xs leading-6 text-slate-500">
            4 个旧 vectorbt 模板（均线交叉、RSI 均值回归、时序动量、布林带回归）+ 标普500买入持有基准，
            各 10 万起始资金，按已入库美股日线做日频模拟。老策略保留不删，这里只读查看收益与净值曲线；
            账户启停与订单仍在「交易与模拟 → 手动模拟」。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className={secondaryButtonClass} onClick={() => navigateInvestmentView("trade", undefined, { tab: "paper" })}>
            在手动模拟中查看账户
          </button>
        </div>
      </div>

      {error && <p role="alert" className="mt-3 text-sm text-rose-700">遗留模拟数据读取失败：{error}</p>}
      {loading && !error && <p className="mt-3 text-sm text-slate-400">正在读取遗留模拟账户…</p>}
      {!loading && !error && !rows.length && <p className="mt-3 text-sm text-slate-500">尚未创建遗留模拟账户（需运行 backend/scripts/init_sim.py 并每日 run_sim_day.py）。</p>}

      {rows.length > 0 && (
        <>
          <p className="mt-3 text-[11px] leading-5 text-slate-400">
            起始资金 {money(rows[0].starting_cash)} · 记录 {rows[0].days_logged} 个交易日{lastDate ? ` · 净值截至 ${lastDate}` : ""} · 收益为模拟值，不代表可成交收益。
          </p>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {report?.strategies.map((row) => (
              <button
                key={row.account}
                type="button"
                onClick={() => setSelected(row.account)}
                className={`rounded-xl border p-4 text-left transition hover:border-emerald-300 ${selected === row.account ? "border-emerald-400 bg-emerald-50/60" : "border-slate-200 bg-white"}`}
              >
                <p className="text-sm font-semibold">{row.label ?? row.account}</p>
                <p className="mt-1 text-[10px] text-slate-400">{row.account}</p>
                <dl className="mt-3 grid grid-cols-3 gap-2 text-xs">
                  <div><dt className="text-slate-400">参考权益</dt><dd className="mt-1 font-medium">{money(row.equity)}</dd></div>
                  <div><dt className="text-slate-400">累计收益</dt><dd className={`mt-1 font-medium ${pctClass(row.total_return_pct)}`}>{pct(row.total_return_pct)}</dd></div>
                  <div><dt className="text-slate-400">相对基准</dt><dd className={`mt-1 font-medium ${pctClass(row.vs_spy_pct)}`}>{pct(row.vs_spy_pct)}</dd></div>
                </dl>
              </button>
            ))}
          </div>
          {report?.benchmark && (
            <div className="mt-3 rounded-xl border border-dashed border-slate-300 bg-slate-50 p-3 text-xs text-slate-600">
              <span className="mr-2 rounded bg-slate-200 px-1.5 py-0.5 text-[10px]">基准</span>
              {report.benchmark.label ?? report.benchmark.account} · 参考权益 {money(report.benchmark.equity)} · 累计收益{" "}
              <span className={pctClass(report.benchmark.total_return_pct)}>{pct(report.benchmark.total_return_pct)}</span>
              （其它策略的「相对基准」= 策略收益 − 该基准收益）
            </div>
          )}

          {chosen && (
            <div className="mt-4 rounded-xl border border-slate-200 bg-white p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h4 className="font-semibold">{chosen.label ?? chosen.account} · 净值曲线</h4>
                  <p className="mt-1 text-[10px] text-slate-400">{chosen.account} · {chosen.days_logged} 个交易日 · 起始 {money(chosen.starting_cash)}</p>
                </div>
                <button className={secondaryButtonClass} onClick={() => setSelected(null)}>收起</button>
              </div>
              {hasChartData ? <LegacySimChart curves={curves} rows={rows} selectedAccount={chosen.account}/> : <p className="mt-3 text-sm text-slate-500">该账户还没有净值记录。</p>}
              <p className="mt-2 text-[11px] leading-5 text-slate-400">
                只读视图：不启动/暂停账户、不产生模拟订单；如需查看订单与持仓，去「交易与模拟 → 手动模拟」。
              </p>
            </div>
          )}
        </>
      )}
    </Card>
  );
}
