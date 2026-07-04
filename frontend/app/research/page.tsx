"use client";

import { useState } from "react";

import { api, type ResearchNote } from "@/lib/api";

export default function ResearchPage() {
  const [symbol, setSymbol] = useState("600519");
  const [note, setNote] = useState<ResearchNote | null>(null);
  const [status, setStatus] = useState("");

  async function fetchNote() {
    setStatus("asking the LLM for a structured thesis...");
    setNote(null);
    try {
      const result = await api.getResearchNote(symbol);
      setNote(result);
      setStatus(result.cache_hit ? "served from cache" : `generated (retries: ${result.retries})`);
    } catch (e) {
      setStatus(String(e));
    }
  }

  return (
    <main className="max-w-3xl mx-auto p-10">
      <h1 className="text-2xl font-medium">LLM research assistant</h1>
      <p className="text-sm text-gray-500 mt-1">
        Structured thesis / catalysts / risks / fair value, Pydantic-schema validated with automatic
        retry on failure, Redis-cached per ticker for 24h.
      </p>
      <p className="text-xs text-amber-600 mt-2">
        Requires a real ANTHROPIC_API_KEY in the backend&apos;s environment — without one this will
        return a clear error rather than a fabricated note.
      </p>

      <div className="mt-6 flex gap-2 items-end">
        <label className="text-sm">
          Symbol
          <input className="border rounded px-2 py-1 block" value={symbol} onChange={(e) => setSymbol(e.target.value)} />
        </label>
        <button className="border rounded px-3 py-1 bg-black text-white" onClick={fetchNote}>
          Get research note
        </button>
      </div>

      {status && <p className="mt-3 text-sm text-gray-600">{status}</p>}

      {note && (
        <div className="mt-8 space-y-4">
          <section>
            <h2 className="font-medium">Thesis</h2>
            <p className="text-sm mt-1">{note.thesis}</p>
          </section>
          <section>
            <h2 className="font-medium">Catalysts</h2>
            <ul className="list-disc list-inside text-sm mt-1">
              {note.catalysts.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </section>
          <section>
            <h2 className="font-medium">Risks</h2>
            <ul className="list-disc list-inside text-sm mt-1">
              {note.risks.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </section>
          <section>
            <h2 className="font-medium">Fair value range</h2>
            <p className="text-sm mt-1">
              {note.fair_value_low} – {note.fair_value_high}
            </p>
          </section>
        </div>
      )}
    </main>
  );
}
