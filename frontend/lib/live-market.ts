"use client";

import { useEffect, useState } from "react";
import { getApiUrl } from "./api";

export type LiveQuote = { code: string; symbol: string; name: string; price: number; pct: number; pe: number | null; pb: number | null; dividend_yield: number | null; quote_time: string; amount_yuan: number | null };
export type QuoteResponse = { quotes: LiveQuote[]; fetched_at: string; provider: string; refresh_seconds: number; missing: string[] };
export const marketApiUrl = () => process.env.NEXT_PUBLIC_CYCLE_API_URL || getApiUrl();

export function useLiveQuotes(codes: string[]) {
  const key = Array.from(new Set(codes.filter(Boolean))).sort().join(",");
  const [data, setData] = useState<QuoteResponse | null>(null), [error, setError] = useState("");
  useEffect(() => {
    if (!key) { setData(null); return; }
    const controller = new AbortController(); let active = true, timer: ReturnType<typeof setTimeout>;
    setData(null);
    async function refresh() {
      let delay = 30;
      try {
        const r = await fetch(`${marketApiUrl()}/market/quotes?symbols=${encodeURIComponent(key)}`, { signal: controller.signal, cache: "no-store" });
        const payload = await r.json(); if (!r.ok) throw new Error(payload.detail || "行情请求失败");
        if (active) { setData(payload); setError(""); delay = payload.refresh_seconds || 30; }
      } catch (e) { if (active && !controller.signal.aborted) { setData(null); setError(e instanceof Error ? e.message : String(e)); } }
      finally { if (active) timer = setTimeout(refresh, delay*1000); }
    }
    refresh();
    return () => { active = false; controller.abort(); clearTimeout(timer); };
  }, [key]);
  return { data, error };
}
