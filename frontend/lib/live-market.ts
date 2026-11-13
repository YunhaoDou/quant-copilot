"use client";

import { useReadResource } from "./read-resource";
import { getApiUrl } from "./api";

export type LiveQuote = { code: string; symbol: string; name: string; price: number; pct: number; pe: number | null; pb: number | null; dividend_yield: number | null; quote_time: string; amount_yuan: number | null };
export type QuoteResponse = { quotes: LiveQuote[]; fetched_at: string; provider: string; refresh_seconds: number; missing: string[] };
export const marketApiUrl = () => process.env.NEXT_PUBLIC_CYCLE_API_URL || getApiUrl();

export function useLiveQuotes(codes: string[]) {
  const key = Array.from(new Set(codes.filter(Boolean))).sort().join(",");
  return useReadResource<QuoteResponse>(key?`${marketApiUrl()}/market/quotes?symbols=${encodeURIComponent(key)}`:null,d=>(d?.refresh_seconds||30)*1000);
}
