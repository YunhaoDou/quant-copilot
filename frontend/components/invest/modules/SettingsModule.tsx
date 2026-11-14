"use client";
import RuntimeStatusPanel from "../RuntimeStatusPanel";
import WorkspaceTabs from "../WorkspaceTabs";
import ResearchLabModule from "./ResearchLabModule";

import { useEffect, useState } from "react";

import { api, getApiUrl, setApiUrl } from "@/lib/api";
import { useLocale } from "@/lib/i18n";
import { navigateInvestmentView } from "@/lib/invest-navigation";

export default function SettingsModule() {return <WorkspaceTabs label="系统设置功能" tabs={[{id:"connection",label:"连接与缓存",content:<ConnectionSettings/>},{id:"runtime",label:"运行与性能",content:<RuntimeStatusPanel/>},{id:"models",label:"模型与通知",content:<ResearchLabModule section="模型与通知"/>}]}/>;}

// 模型/LLM 配置（供应商、密钥、模型、LLM 缓存、通知）只在「模型与通知」页签维护（ResearchLabModule → /research-lab/config）。
function goToModels() {
  navigateInvestmentView("help", undefined, { tab: "settings", section: "models" });
}

function ConnectionSettings() {
  const { t } = useLocale();
  const [backendUrl, setBackendUrl] = useState("");
  const [newsCacheTtl, setNewsCacheTtl] = useState(2);
  const [status, setStatus] = useState("");

  useEffect(() => {
    setBackendUrl(getApiUrl());
    api
      .getSettings()
      .then((s) => {
        setNewsCacheTtl(s.news_cache_ttl_hours);
      })
      .catch((e) => setStatus(t("settings.loadError", { err: String(e) })));
  }, [t]);

  async function save() {
    setStatus(t("settings.saving"));
    try {
      await api.updateSettings({ news_cache_ttl_hours: newsCacheTtl });
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
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-950">
          <p>{t("settings.modelsMoved")}</p>
          <button type="button" className="mt-2 text-emerald-800 underline" onClick={goToModels}>
            {t("settings.modelsMovedCta")}
          </button>
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

        <label className="text-sm block">
          {t("settings.newsCacheTtl")}
          <input
            type="number"
            min={0}
            className="border rounded px-2 py-1 block w-full mt-1"
            value={newsCacheTtl}
            onChange={(e) => setNewsCacheTtl(Number(e.target.value))}
          />
        </label>

        <button className="border rounded px-4 py-1.5 bg-black text-white text-sm" onClick={save}>
          {t("settings.save")}
        </button>
        {status && <p className="text-sm text-gray-600">{status}</p>}
      </div>
    </main>
  );
}
