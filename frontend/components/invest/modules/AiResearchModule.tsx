"use client";

import { useState } from "react";

import { api, type ResearchNote } from "@/lib/api";
import { useLocale } from "@/lib/i18n";

export default function AiResearchModule() {
  const { locale, t } = useLocale();
  const [symbol, setSymbol] = useState("600519.SS");
  const [note, setNote] = useState<ResearchNote | null>(null);
  const [status, setStatus] = useState("");

  async function fetchNote() {
    setStatus(t("research.asking"));
    setNote(null);
    try {
      const result = await api.getResearchNote(symbol, locale);
      setNote(result);
      setStatus(result.cache_hit ? t("research.cached") : t("research.generated", { n: result.retries }));
    } catch (e) {
      setStatus(String(e));
    }
  }

  return (
    <main className="max-w-3xl mx-auto p-10">
      <h1 className="text-2xl font-medium">{t("research.title")}</h1>
      <p className="text-sm text-gray-500 mt-1">{t("research.desc")}</p>
      <p className="text-xs text-amber-600 mt-2">{t("research.warn")}</p>

      <div className="mt-6 flex gap-2 items-end">
        <label className="text-sm">
          {t("research.symbol")}
          <input className="border rounded px-2 py-1 block" value={symbol} onChange={(e) => setSymbol(e.target.value)} />
        </label>
        <button className="border rounded px-3 py-1 bg-black text-white" onClick={fetchNote}>
          {t("research.fetch")}
        </button>
      </div>

      {status && <p className="mt-3 text-sm text-gray-600">{status}</p>}

      {note && (
        <div className="mt-8 space-y-4">
          <section>
            <h2 className="font-medium">{t("research.thesis")}</h2>
            <p className="text-sm mt-1">{note.thesis}</p>
          </section>
          <section>
            <h2 className="font-medium">{t("research.catalysts")}</h2>
            <ul className="list-disc list-inside text-sm mt-1">
              {note.catalysts.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </section>
          <section>
            <h2 className="font-medium">{t("research.risks")}</h2>
            <ul className="list-disc list-inside text-sm mt-1">
              {note.risks.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </section>
          <section>
            <h2 className="font-medium">{t("research.fairValue")}</h2>
            <p className="text-sm mt-1">
              {note.fair_value_low} – {note.fair_value_high}
            </p>
          </section>
        </div>
      )}
    </main>
  );
}
