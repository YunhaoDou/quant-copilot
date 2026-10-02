"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { INVESTMENT_VIEW_EVENT, INVESTMENT_VIEWS, InvestmentView, navigateInvestmentView, readInvestmentView } from "@/lib/invest-navigation";
import { useLocale } from "@/lib/i18n";

export default function Navbar() {
  const [active, setActive] = useState<InvestmentView>("dashboard");
  const { locale, setLocale } = useLocale();

  useEffect(() => {
    const sync = () => setActive(readInvestmentView());
    sync();
    window.addEventListener("popstate", sync);
    window.addEventListener(INVESTMENT_VIEW_EVENT, sync);
    return () => {
      window.removeEventListener("popstate", sync);
      window.removeEventListener(INVESTMENT_VIEW_EVENT, sync);
    };
  }, []);

  const activeItem = INVESTMENT_VIEWS.find((item) => item.id === active) ?? INVESTMENT_VIEWS[0];

  return (
    <>
      <header className="fixed inset-x-0 top-0 z-50 flex h-14 items-center justify-between border-b border-slate-200/80 bg-white/90 px-4 backdrop-blur-xl lg:hidden">
        <Link href="/invest?view=dashboard" className="flex items-center gap-2.5 text-slate-950">
          <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-[#173f2c] text-sm font-semibold text-white">Q</span>
          <span><strong className="block text-sm leading-4">A股投资系统</strong><small className="text-[11px] text-slate-400">{activeItem.label}</small></span>
        </Link>
        <button className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-500" onClick={() => setLocale(locale === "en" ? "zh" : "en")}>{locale === "en" ? "中文" : "EN"}</button>
      </header>

      <aside className="fixed inset-y-0 left-0 z-50 hidden w-60 flex-col border-r border-slate-200/80 bg-[#fbfcfa] lg:flex">
        <Link href="/invest?view=dashboard" className="flex h-20 shrink-0 items-center gap-3 border-b border-slate-100 px-5">
          <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[#173f2c] text-base font-semibold text-white shadow-sm">Q</span>
          <span><strong className="block text-[15px] tracking-tight text-slate-950">A股投资系统</strong><small className="text-[11px] text-slate-400">Personal Investment OS</small></span>
        </Link>

        <nav className="flex-1 overflow-y-auto px-3 py-5">
          {(["决策", "工具"] as const).map((group) => (
            <div key={group} className="mb-5">
              <p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-400">{group}</p>
              <div className="space-y-1">
                {INVESTMENT_VIEWS.filter((item) => item.group === group).map((item) => (
                  <a
                    key={item.id}
                    href={`/invest?view=${item.id}`}
                    onClick={(event) => { event.preventDefault(); navigateInvestmentView(item.id); }}
                    className={`group flex items-center gap-3 rounded-xl px-3 py-2.5 transition ${active === item.id ? "bg-[#e8f2eb] text-[#173f2c]" : "text-slate-600 hover:bg-white hover:text-slate-950"}`}
                  >
                    <span className={`h-2 w-2 shrink-0 rounded-full transition ${active === item.id ? "bg-emerald-600 shadow-[0_0_0_4px_rgba(5,150,105,0.1)]" : "bg-slate-300 group-hover:bg-slate-400"}`} />
                    <span className="min-w-0"><strong className="block text-sm font-medium">{item.label}</strong><small className={`block truncate text-[11px] ${active === item.id ? "text-emerald-700/70" : "text-slate-400"}`}>{item.description}</small></span>
                  </a>
                ))}
              </div>
            </div>
          ))}
        </nav>

        <div className="border-t border-slate-100 p-3">
          <div className="rounded-2xl border border-slate-200/80 bg-white p-3">
            <div className="flex items-center justify-between"><span className="text-xs font-medium text-slate-600">A股本地工作区</span><span className="h-2 w-2 rounded-full bg-emerald-500" /></div>
            <p className="mt-1 text-[11px] leading-5 text-slate-400">人民币 · 20%回撤防线<br />数据保存在当前浏览器</p>
          </div>
          <button className="mt-2 w-full rounded-xl px-3 py-2 text-xs font-medium text-slate-500 transition hover:bg-slate-100" onClick={() => setLocale(locale === "en" ? "zh" : "en")}>{locale === "en" ? "切换到中文" : "Switch to English"}</button>
        </div>
      </aside>
    </>
  );
}
