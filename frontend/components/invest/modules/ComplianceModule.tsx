"use client";

import { useState } from "react";

import { api, type ComplianceAnswer } from "@/lib/api";
import { useLocale } from "@/lib/i18n";

// Retrieval is TF-IDF over an English-only corpus, so sample questions are always submitted
// in English regardless of UI language (only their button label is localized) — otherwise a
// Chinese-locale click would return "not covered" for a question the corpus actually answers.
const ENGLISH_SAMPLE_QUESTIONS = [
  "How many day trades before I'm flagged as a pattern day trader?",
  "What options level do I need to sell uncovered naked calls?",
  "Can I recommend a leveraged product to a conservative, low-risk-tolerance customer?",
];
const SAMPLE_KEYS = ["compliance.sample1", "compliance.sample2", "compliance.sample3"];

export default function ComplianceModule() {
  const { locale, t } = useLocale();
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<ComplianceAnswer | null>(null);
  const [status, setStatus] = useState("");

  async function ask(q?: string) {
    const query = q ?? question;
    if (!query.trim()) return;
    setQuestion(query);
    setStatus(t("compliance.searching"));
    setResult(null);
    try {
      const r = await api.askCompliance(query, locale);
      setResult(r);
      setStatus(r.cache_hit ? t("compliance.cached") : r.grounded ? t("compliance.grounded") : t("compliance.notCovered"));
    } catch (e) {
      setStatus(String(e));
    }
  }

  return (
    <main className="max-w-3xl mx-auto p-10">
      <h1 className="text-2xl font-medium">{t("compliance.title")}</h1>
      <p className="text-sm text-gray-500 mt-1">{t("compliance.desc")}</p>
      <p className="text-xs text-amber-600 mt-2">{t("compliance.warn")}</p>
      {t("compliance.hint") && <p className="text-xs text-gray-400 mt-2">{t("compliance.hint")}</p>}

      <div className="mt-6 flex gap-2 items-end">
        <label className="text-sm flex-1">
          {t("compliance.question")}
          <input
            className="border rounded px-2 py-1 block w-full"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && ask()}
          />
        </label>
        <button className="border rounded px-3 py-1 bg-black text-white" onClick={() => ask()}>
          {t("compliance.ask")}
        </button>
      </div>

      <div className="mt-2 flex flex-wrap gap-1.5">
        {ENGLISH_SAMPLE_QUESTIONS.map((q, i) => (
          <button
            key={q}
            className="text-xs border rounded-full px-2.5 py-1 text-gray-500 hover:bg-gray-50"
            onClick={() => ask(q)}
          >
            {t(SAMPLE_KEYS[i])}
          </button>
        ))}
      </div>

      {status && <p className="mt-3 text-sm text-gray-600">{status}</p>}

      {result && (
        <div className="mt-8 space-y-3">
          <p className="text-sm">{result.answer}</p>
          {result.citations.length > 0 && (
            <p className="text-xs text-gray-400">{t("compliance.sources", { list: result.citations.join(", ") })}</p>
          )}
        </div>
      )}
    </main>
  );
}
