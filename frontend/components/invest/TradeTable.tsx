"use client";
import type { ReactNode } from "react";
import { money } from "./ui";
import { tradeSideLabel, type TradeView } from "@/lib/account-view";

export type TradeColumn = {
  key: string;
  label: string;
  render: (trade: TradeView) => ReactNode;
  className?: string;
};

export type TradeColumnKey = "time" | "symbol" | "side" | "price" | "quantity" | "pnl" | "fee" | "reason";

const CANONICAL_COLUMNS: Record<TradeColumnKey, { label: string; render: (trade: TradeView) => ReactNode }> = {
  time: { label: "时间", render: (trade) => trade.time },
  symbol: { label: "股票", render: (trade) => (trade.name ? `${trade.name} ${trade.symbol}` : trade.symbol) },
  side: { label: "方向", render: (trade) => tradeSideLabel(trade.side) },
  price: { label: "模拟价格", render: (trade) => trade.price.toFixed(3) },
  quantity: { label: "股数", render: (trade) => trade.quantity },
  pnl: { label: "净盈亏", render: (trade) => (trade.pnl === null || trade.pnl === undefined ? "—" : money(trade.pnl)) },
  fee: { label: "费用", render: (trade) => (trade.fee === undefined ? "—" : trade.fee.toFixed(2)) },
  reason: {
    label: "原因",
    render: (trade) => (
      <>
        {trade.reason}
        {trade.note && <span className="block text-slate-500">范围：{trade.note}</span>}
      </>
    ),
  },
};

/** Build one canonical column, optionally with a strategy-specific label. */
export function tradeColumn(key: TradeColumnKey, label?: string): TradeColumn {
  const column = CANONICAL_COLUMNS[key];
  return { key, label: label ?? column.label, render: column.render };
}

/** The full stock-account column set (used by the two A-share strategy panels). */
export function defaultTradeColumns(): TradeColumn[] {
  return [
    tradeColumn("time"),
    tradeColumn("symbol"),
    tradeColumn("side"),
    tradeColumn("price"),
    tradeColumn("quantity"),
    tradeColumn("pnl"),
    tradeColumn("reason"),
  ];
}

export type TradeTableProps = {
  rows: TradeView[] | null | undefined;
  /** Column set; defaults to the full stock-account columns. */
  columns?: TradeColumn[];
  emptyText?: ReactNode;
  minWidthClass?: string;
};

/**
 * Shared simulated-trade table. Columns are configurable so each strategy keeps
 * its own fields (SHIBOR fee/slippage price, TrendLeader forward rows, ...)
 * while the A-share panels share the canonical column set and labels.
 */
export default function TradeTable({
  rows,
  columns = defaultTradeColumns(),
  emptyText = "尚无模拟成交，等待有效信号和后续可成交报价。",
  minWidthClass = "min-w-[620px]",
}: TradeTableProps) {
  const list = rows ?? [];
  return (
    <>
      <div className="mt-3 overflow-x-auto">
        <table className={`w-full ${minWidthClass} text-left text-xs`}>
          <thead>
            <tr>
              {columns.map((column) => (
                <th className="py-2" key={column.key}>
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {list.map((trade, index) => (
              <tr className="border-t" key={index}>
                {columns.map((column) => (
                  <td className={`py-2 ${column.className ?? ""}`} key={column.key}>
                    {column.render(trade)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!list.length && <p className="mt-3 text-sm text-slate-500">{emptyText}</p>}
    </>
  );
}
