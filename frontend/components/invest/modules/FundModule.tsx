"use client";
import EtfTrackerPanel from "../EtfTrackerPanel";
import WorkspaceTabs from "../WorkspaceTabs";
import ResearchLabModule from "./ResearchLabModule";

import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { api, type FundAnalysis, type FundListing, type FundNavPoint } from "@/lib/api";
import { useLocale } from "@/lib/i18n";
import LiveQuotes from "../live-quotes";

const ALERT_CLASS: Record<string, string> = {
  normal: "bg-gray-50 text-gray-600",
  warning: "bg-yellow-50 text-yellow-700",
  danger: "bg-red-50 text-red-700",
};

export default function FundModule() {return <WorkspaceTabs label="基金与ETF功能" tabs={[{id:"etf-universe",label:"全ETF追踪",content:<EtfTrackerPanel/>},{id:"fund-overview",label:"净值与折溢价",content:<FundOverview/>},{id:"fund-research",label:"基金深研与比较",content:<ResearchLabModule section="基金深研"/>}]}/>;}

const sourceErrorLabels:Record<string,string>={timeout:"请求超时",rate_limited:"源端限流",connection_error:"连接中断",http_error:"接口错误",invalid_response:"响应不完整",code_mismatch:"证券代码不匹配",invalid_price:"价格无效"};

function FundOverview() {
  const { t } = useLocale();
  const [code, setCode] = useState("510300");
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
      <LiveQuotes codes={[code]} />
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
          {analysis.premium_status && analysis.premium_status.state!=="available" && <p role="status" className="mt-4 text-sm text-amber-800">{analysis.premium_status.message}{analysis.premium_status.category&&` · ${sourceErrorLabels[analysis.premium_status.category]||"数据源异常"}`}</p>}
          {analysis.premium && (
            <div className={`mt-8 rounded-lg px-4 py-3 text-sm ${ALERT_CLASS[analysis.premium.alert_level]}`}>
              <div className="font-medium">
                {t("fund.premiumRate")}: {analysis.premium.premium_rate.toFixed(2)}% ({t("fund.price")}{" "}
                {analysis.premium.price.toFixed(3)} / IOPV {analysis.premium.iopv.toFixed(3)})
              </div>
              <div className="mt-0.5">{analysis.premium.alert_message}</div>
              <div className="mt-1 text-xs">{analysis.premium.provider||"公开源"} · IOPV快照时间：{analysis.premium.quote_time ? new Date(analysis.premium.quote_time).toLocaleString("zh-CN") : "供应商未提供"}，点击加载可重新获取。<span className="block">同供应商备用节点不代表独立来源核验；价格与IOPV来自同一响应，不跨源拼接。{analysis.premium.fetched_at&&`采集：${new Date(analysis.premium.fetched_at).toLocaleString("zh-CN")}`}</span></div>
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
