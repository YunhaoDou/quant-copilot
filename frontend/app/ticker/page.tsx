"use client";

import { useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { api, type PricePoint } from "@/lib/api";

export default function TickerPage() {
  const [symbol, setSymbol] = useState("600519");
  const [name, setName] = useState("贵州茅台");
  const [prices, setPrices] = useState<PricePoint[]>([]);
  const [status, setStatus] = useState<string>("");

  async function handleIngestAndLoad() {
    setStatus("ingesting...");
    try {
      await api.ingestTicker(symbol, name);
      const data = await api.getPrices(symbol);
      setPrices(data);
      setStatus(`loaded ${data.length} bars`);
    } catch (e) {
      setStatus(String(e));
    }
  }

  async function handleLoadOnly() {
    setStatus("loading...");
    try {
      const data = await api.getPrices(symbol);
      setPrices(data);
      setStatus(`loaded ${data.length} bars`);
    } catch (e) {
      setStatus(String(e));
    }
  }

  return (
    <main className="max-w-4xl mx-auto p-10">
      <h1 className="text-2xl font-medium">Ticker price history</h1>
      <p className="text-sm text-gray-500 mt-1">Real A-share OHLCV pulled via akshare, stored in Postgres.</p>

      <div className="mt-6 flex gap-2 items-end">
        <label className="text-sm">
          Symbol
          <input className="border rounded px-2 py-1 block" value={symbol} onChange={(e) => setSymbol(e.target.value)} />
        </label>
        <label className="text-sm">
          Name (for first ingest)
          <input className="border rounded px-2 py-1 block" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <button className="border rounded px-3 py-1 bg-black text-white" onClick={handleIngestAndLoad}>
          Ingest + load
        </button>
        <button className="border rounded px-3 py-1" onClick={handleLoadOnly}>
          Load only
        </button>
      </div>

      {status && <p className="mt-3 text-sm text-gray-600">{status}</p>}

      {prices.length > 0 && (
        <div className="mt-8" style={{ height: 360 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={prices}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={40} />
              <YAxis domain={["auto", "auto"]} tick={{ fontSize: 10 }} />
              <Tooltip />
              <Line type="monotone" dataKey="close" stroke="#2563eb" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </main>
  );
}
