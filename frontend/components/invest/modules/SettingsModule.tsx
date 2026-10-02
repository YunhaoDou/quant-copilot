"use client";

import { useEffect, useState } from "react";

import { api, getApiUrl, setApiUrl, type AppSettingsView } from "@/lib/api";
import { useLocale } from "@/lib/i18n";

export default function SettingsModule() {
  const { t } = useLocale();
  const [current, setCurrent] = useState<AppSettingsView | null>(null);
  const [deepseekKey, setDeepseekKey] = useState("");
  const [backendUrl, setBackendUrl] = useState("");
  const [newsCacheTtl, setNewsCacheTtl] = useState(2);
  const [llmCacheTtl, setLlmCacheTtl] = useState(24);
  const [status, setStatus] = useState("");

  useEffect(() => {
    setBackendUrl(getApiUrl());
    api
      .getSettings()
      .then((s) => {
        setCurrent(s);
        setNewsCacheTtl(s.news_cache_ttl_hours);
        setLlmCacheTtl(s.llm_cache_ttl_hours);
      })
      .catch((e) => setStatus(t("settings.loadError", { err: String(e) })));
  }, [t]);

  async function save() {
    setStatus(t("settings.saving"));
    try {
      const updated = await api.updateSettings({
        deepseek_api_key: deepseekKey.trim() || undefined,
        news_cache_ttl_hours: newsCacheTtl,
        llm_cache_ttl_hours: llmCacheTtl,
      });
      setCurrent(updated);
      setDeepseekKey("");
      if (backendUrl.trim()) setApiUrl(backendUrl.trim());
      setStatus(t("settings.saved"));
    } catch (e) {
      setStatus(String(e));
    }
  }

  return (
    <main className="max-w-2xl mx-auto p-10">
      <h1 className="text-2xl font-medium">{t("settings.title")}</h1>
      <p className="text-sm text-gray-500 mt-1">{t("settings.desc")}</p>

      <div className="mt-8 space-y-6">
        <div>
          <label className="text-sm font-medium">{t("settings.deepseekKey")}</label>
          <p className="text-xs text-gray-500 mt-0.5">
            {current
              ? current.deepseek_api_key_set
                ? t("settings.deepseekKeySet", { last4: current.deepseek_api_key_masked.slice(-4) })
                : t("settings.deepseekKeyNotSet")
              : ""}
          </p>
          <input
            type="password"
            className="border rounded px-2 py-1 mt-2 block w-full"
            placeholder={t("settings.deepseekKeyPlaceholder")}
            value={deepseekKey}
            onChange={(e) => setDeepseekKey(e.target.value)}
          />
        </div>

        <div>
          <label className="text-sm font-medium">{t("settings.backendUrl")}</label>
          <p className="text-xs text-gray-500 mt-0.5">{t("settings.backendUrlDesc")}</p>
          <input
            className="border rounded px-2 py-1 mt-2 block w-full"
            value={backendUrl}
            onChange={(e) => setBackendUrl(e.target.value)}
          />
        </div>

        <div className="flex gap-4">
          <label className="text-sm flex-1">
            {t("settings.newsCacheTtl")}
            <input
              type="number"
              min={0}
              className="border rounded px-2 py-1 block w-full mt-1"
              value={newsCacheTtl}
              onChange={(e) => setNewsCacheTtl(Number(e.target.value))}
            />
          </label>
          <label className="text-sm flex-1">
            {t("settings.llmCacheTtl")}
            <input
              type="number"
              min={0}
              className="border rounded px-2 py-1 block w-full mt-1"
              value={llmCacheTtl}
              onChange={(e) => setLlmCacheTtl(Number(e.target.value))}
            />
          </label>
        </div>

        <button className="border rounded px-4 py-1.5 bg-black text-white text-sm" onClick={save}>
          {t("settings.save")}
        </button>
        {status && <p className="text-sm text-gray-600">{status}</p>}
      </div>
    </main>
  );
}
