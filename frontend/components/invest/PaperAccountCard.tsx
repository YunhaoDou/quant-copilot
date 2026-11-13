"use client";
import type { ReactNode } from "react";
import { Card, buttonClass, money, secondaryButtonClass } from "./ui";
import { accountDrawdown, type AccountView } from "@/lib/account-view";

export type PaperAccountAction = {
  id: string;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  /** Primary styling for the "start" action (default: secondary, like pause/exit). */
  primary?: boolean;
};

export type PaperAccountCardProps = {
  title: ReactNode;
  /** Normalized account; null means the strategy account has not been started. */
  account: AccountView | null;
  /** Start/pause/exit controls; disabled state is decided by the panel. */
  actions?: PaperAccountAction[];
  busy?: boolean;
  error?: string | null;
  /** Short intro under the heading (SHIBOR's strategy blurb). */
  description?: ReactNode;
  /** Optional status line under the heading (e.g. "账户：运行中 · 后台：running"). */
  statusLine?: ReactNode;
  /** Strategy-specific metadata under the capital grid (rules, dates, fees, warnings). */
  meta?: ReactNode;
  /** Strategy-specific position line. */
  position?: ReactNode;
  /** Strategy-specific pending-order line. */
  pending?: ReactNode;
  headingLevel?: 3 | 4;
  /** Render the content as a plain section instead of its own Card (nested panels). */
  bare?: boolean;
  className?: string;
};

/**
 * Shared "independent paper account" card: status, initial capital / cash /
 * equity / drawdown, start-pause-exit controls and the load error. Strategy
 * specific content is injected through the description/meta/position/pending
 * slots so each panel stays a thin adapter over its own API payload.
 */
export default function PaperAccountCard({
  title,
  account,
  actions,
  busy,
  error,
  description,
  statusLine,
  meta,
  position,
  pending,
  headingLevel = 4,
  bare,
  className = "",
}: PaperAccountCardProps) {
  const Heading = headingLevel === 3 ? "h3" : "h4";
  const headingClass = headingLevel === 3 ? "text-xl font-semibold" : "font-semibold";

  const body = (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Heading className={headingClass}>{title}</Heading>
        {actions && actions.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {actions.map((action) => (
              <button
                key={action.id}
                type="button"
                disabled={busy || action.disabled}
                className={action.primary ? buttonClass : secondaryButtonClass}
                onClick={action.onClick}
              >
                {action.label}
              </button>
            ))}
          </div>
        )}
      </div>
      {description && <p className="mt-2 text-sm leading-7 text-slate-600">{description}</p>}
      {statusLine && <p className="mt-3 text-sm">{statusLine}</p>}
      {error && (
        <p role="alert" className="mt-3 text-sm text-red-700">
          {error}
        </p>
      )}
      {account && (
        <>
          <div className="mt-4 grid gap-3 sm:grid-cols-4">
            <AccountStat label="初始资金" value={money(account.capital)} />
            <AccountStat label="现金" value={money(account.cash)} />
            <AccountStat label="参考权益" value={money(account.equity)} />
            <AccountStat label="回撤" value={accountDrawdown(account)} />
          </div>
          {meta}
          {position}
          {pending}
        </>
      )}
    </>
  );

  return bare ? (
    <section className={`min-w-0 ${className}`}>{body}</section>
  ) : (
    <Card className={className}>{body}</Card>
  );
}

function AccountStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-1 text-xl font-semibold">{value}</p>
    </div>
  );
}
