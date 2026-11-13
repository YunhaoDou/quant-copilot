"use client";
import { useEffect, useState, type ReactNode } from "react";
import { INVESTMENT_VIEW_EVENT } from "@/lib/invest-navigation";
import { buttonClass, secondaryButtonClass } from "./ui";

/**
 * 工作流页面内的子页签。默认读写 ?section=；顶层页面用 param="tab"，
 * 这样内层面板（红利/研究/基金/设置等）继续用自己的 ?section= 互不干扰。
 */
export default function WorkspaceTabs({
  label,
  tabs,
  param = "section",
}: {
  label: string;
  tabs: { id: string; label: string; content: ReactNode }[];
  param?: string;
}) {
  const [synced,setSynced] = useState(false);
  const [active, setActive] = useState(tabs[0].id);
  const tabIds = tabs.map((t) => t.id).join(",");
  useEffect(() => {
    const sync = () => {
      const value = new URLSearchParams(window.location.search).get(param);
      setSynced(true);
      setActive(tabs.some((t) => t.id === value) ? (value as string) : tabs[0].id);
    };
    sync();
    window.addEventListener("popstate", sync);
    window.addEventListener(INVESTMENT_VIEW_EVENT, sync);
    return () => {
      window.removeEventListener("popstate", sync);
      window.removeEventListener(INVESTMENT_VIEW_EVENT, sync);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tabIds, param]);
  function select(id: string) {
    setActive(id);
    const url = new URL(window.location.href);
    url.searchParams.set(param, id);
    window.history.pushState({}, "", url);
  }
  return (
    <div className="space-y-5">
      <nav aria-label={label} className="flex flex-wrap gap-2">
        {tabs.map((t) => (
          <button
            key={t.id}
            aria-pressed={active === t.id}
            className={active === t.id ? buttonClass : secondaryButtonClass}
            onClick={() => select(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>
      <div className="min-w-0 [&>main]:max-w-none [&>main]:p-0">
        {synced && (tabs.find((t) => t.id === active) || tabs[0]).content}
      </div>
    </div>
  );
}
