import type { ReactNode } from "react";

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-[20px] border border-slate-200/80 bg-white p-5 shadow-[0_10px_30px_rgba(15,23,42,0.045)] ${className}`}
    >
      {children}
    </section>
  );
}

export function Metric({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "default" | "good" | "warn" | "danger";
}) {
  const toneClass = {
    default: "text-slate-900",
    good: "text-emerald-700",
    warn: "text-amber-700",
    danger: "text-red-700",
  }[tone];
  return (
    <div className="rounded-2xl border border-slate-200/70 bg-[#f8f9f7] p-4">
      <div className="text-xs font-medium tracking-wide text-slate-500">{label}</div>
      <div className={`mt-1.5 text-2xl font-semibold tracking-tight tabular-nums ${toneClass}`}>{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-slate-600">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-400">{hint}</span>}
    </label>
  );
}

export const inputClass =
  "w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-emerald-600 focus:ring-4 focus:ring-emerald-100/70";

export const buttonClass =
  "rounded-xl bg-[#173f2c] px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-[#102f21] focus:outline-none focus:ring-4 focus:ring-emerald-100 disabled:cursor-not-allowed disabled:opacity-50";

export const secondaryButtonClass =
  "rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-sm font-medium text-slate-700 transition hover:border-slate-400 hover:bg-slate-50 focus:outline-none focus:ring-4 focus:ring-slate-100";

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-300 bg-[#fafbf9] px-6 py-10 text-center text-sm text-slate-500">
      <div className="mx-auto mb-3 flex h-9 w-9 items-center justify-center rounded-full bg-slate-100 text-lg text-slate-400">+</div>
      <div>{children}</div>
    </div>
  );
}

export function ProgressBar({ value, color = "bg-emerald-500" }: { value: number; color?: string }) {
  return (
    <div className="h-2.5 overflow-hidden rounded-full bg-slate-100">
      <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
    </div>
  );
}

export function money(value: number) {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
    maximumFractionDigits: 0,
  }).format(Number.isFinite(value) ? value : 0);
}
