"use client";

import { useCallback, useEffect, useState } from "react";

import {
  api,
  type OrderInput,
  type PaperAccount,
  type PaperOrder,
  type PaperSnapshot,
  type RiskSnapshot,
} from "@/lib/api";
import { useLocale } from "@/lib/i18n";

const money = (n: number) =>
  n.toLocaleString("zh-CN", { style: "currency", currency: "CNY", maximumFractionDigits: 2 });

const pnlColor = (n: number) => (n > 0 ? "text-green-600" : n < 0 ? "text-red-600" : "text-gray-500");

export default function PaperModule() {
  const { t } = useLocale();
  const [accounts, setAccounts] = useState<PaperAccount[]>([]);
  const [accountId, setAccountId] = useState<number | null>(null);
  const [snapshot, setSnapshot] = useState<PaperSnapshot | null>(null);
  const [orders, setOrders] = useState<PaperOrder[]>([]);
  const [risk, setRisk] = useState<RiskSnapshot | null>(null);
  const [status, setStatus] = useState("");

  // new-account form
  const [newName, setNewName] = useState("");
  const [newCash, setNewCash] = useState(100000);

  // order form
  const [symbol, setSymbol] = useState("600519.SS");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [orderType, setOrderType] = useState<"market" | "limit" | "stop">("market");
  const [quantity, setQuantity] = useState(10);
  const [limitPrice, setLimitPrice] = useState<number>(0);

  const refreshAccounts = useCallback(async () => {
    try {
      const list = await api.listAccounts();
      setAccounts(list);
      setAccountId((prev) => prev ?? (list.length ? list[0].id : null));
    } catch (e) {
      setStatus(String(e));
    }
  }, []);

  const refreshAccountView = useCallback(async (id: number) => {
    try {
      const [snap, ords, rsk] = await Promise.all([
        api.getSnapshot(id),
        api.listOrders(id),
        api.getRisk(id),
      ]);
      setSnapshot(snap);
      setOrders(ords);
      setRisk(rsk);
    } catch (e) {
      setStatus(String(e));
    }
  }, []);

  useEffect(() => {
    refreshAccounts();
  }, [refreshAccounts]);

  useEffect(() => {
    if (accountId != null) refreshAccountView(accountId);
  }, [accountId, refreshAccountView]);

  async function createAccount() {
    if (!newName.trim()) {
      setStatus(t("paper.accountNameRequired"));
      return;
    }
    try {
      const acct = await api.createAccount(newName.trim(), newCash);
      setNewName("");
      await refreshAccounts();
      setAccountId(acct.id);
      setStatus(t("paper.created", { name: acct.name }));
    } catch (e) {
      setStatus(String(e));
    }
  }

  async function submitOrder() {
    if (accountId == null) {
      setStatus(t("paper.selectOrCreate"));
      return;
    }
    const order: OrderInput = {
      symbol: symbol.trim().toUpperCase(),
      side,
      quantity,
      order_type: orderType,
      limit_price: orderType === "market" ? null : limitPrice,
    };
    try {
      const placed = await api.placeOrder(accountId, order);
      setStatus(
        placed.status === "filled"
          ? t("paper.filled", { side: t(`paper.${placed.side}`), qty: placed.quantity, symbol: placed.symbol, price: money(placed.fill_price ?? 0) })
          : t("paper.rejected", { reason: placed.reason ?? "" }),
      );
      await refreshAccountView(accountId);
    } catch (e) {
      setStatus(String(e));
    }
  }

  return (
    <main className="max-w-5xl mx-auto p-10">
      <h1 className="text-2xl font-medium">{t("paper.title")}</h1>
      <p className="text-sm text-gray-500 mt-1">{t("paper.desc")}</p>
      <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">当前撮合器按最新收盘价进行研究性模拟，尚未实现A股T+1、100股一手和涨跌停限制，请勿把结果视为真实可成交订单。</p>

      {/* Account selector + creation */}
      <section className="mt-6 flex flex-wrap gap-6 items-end">
        <label className="text-sm">
          {t("paper.account")}
          <select
            className="border rounded px-2 py-1 block min-w-48"
            value={accountId ?? ""}
            onChange={(e) => setAccountId(e.target.value ? Number(e.target.value) : null)}
          >
            {accounts.length === 0 && <option value="">{t("paper.noAccounts")}</option>}
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name} ({money(a.cash_balance)} cash)
              </option>
            ))}
          </select>
        </label>

        <div className="flex gap-2 items-end">
          <label className="text-sm">
            {t("paper.newAccount")}
            <input
              className="border rounded px-2 py-1 block"
              placeholder={t("paper.namePlaceholder")}
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
            />
          </label>
          <label className="text-sm">
            {t("paper.startingCash")}
            <input
              type="number"
              className="border rounded px-2 py-1 block w-32"
              value={newCash}
              onChange={(e) => setNewCash(Number(e.target.value))}
            />
          </label>
          <button className="border rounded px-3 py-1 bg-black text-white" onClick={createAccount}>
            {t("paper.create")}
          </button>
        </div>
      </section>

      {/* Equity summary */}
      {snapshot && (
        <section className="mt-8 grid grid-cols-2 sm:grid-cols-4 gap-4">
          <Stat label={t("paper.totalEquity")} value={money(snapshot.total_equity)} />
          <Stat label={t("paper.cash")} value={money(snapshot.cash_balance)} />
          <Stat label={t("paper.positionsValue")} value={money(snapshot.positions_value)} />
          <Stat
            label={t("paper.totalReturn")}
            value={`${snapshot.total_return_pct.toFixed(2)}%`}
            className={pnlColor(snapshot.total_return_pct)}
          />
        </section>
      )}

      {/* Risk panel (M5) */}
      {risk && risk.num_positions > 0 && (
        <section className="mt-8 border rounded p-4">
          <h2 className="text-lg font-medium">{t("paper.riskPanel")}</h2>

          {risk.alerts.length > 0 ? (
            <ul className="mt-3 space-y-1">
              {risk.alerts.map((a) => (
                <li key={a.code} className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1">
                  ⚠ {a.message}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-green-700">{t("paper.noRiskBreach")}</p>
          )}

          <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-4">
            <Stat label={t("paper.grossExposure")} value={money(risk.gross_exposure)} />
            <Stat label={t("paper.cashPct")} value={`${(risk.cash_pct * 100).toFixed(1)}%`} />
            <Stat label={t("paper.largestPosition")} value={t("paper.ofEquity", { pct: `${(risk.largest_position_weight * 100).toFixed(0)}%` })} />
            <Stat label={t("paper.effectivePositions")} value={t("paper.ofN", { n: risk.effective_positions, total: risk.num_positions })} />
            <Stat
              label={t("paper.maxDrawdownD", { d: risk.drawdown.window_days })}
              value={`${(risk.drawdown.max_drawdown * 100).toFixed(1)}%`}
              className={pnlColor(risk.drawdown.max_drawdown)}
            />
            <Stat label={t("paper.annualizedVol")} value={`${(risk.drawdown.annualized_vol * 100).toFixed(1)}%`} />
            <Stat label={t("paper.hhi")} value={risk.hhi.toFixed(3)} />
            <Stat label={t("paper.top3Weight")} value={`${(risk.top3_weight_of_book * 100).toFixed(0)}%`} />
          </div>

          <table className="mt-5 w-full text-sm border-collapse">
            <thead>
              <tr className="text-left border-b">
                <th className="py-1">{t("paper.symbol")}</th>
                <th>{t("paper.marketValue")}</th>
                <th>{t("paper.weightBook")}</th>
                <th>{t("paper.weightEquity")}</th>
              </tr>
            </thead>
            <tbody>
              {risk.exposures.map((e) => (
                <tr key={e.symbol} className="border-b">
                  <td className="py-1 font-medium">{e.symbol}</td>
                  <td>{money(e.market_value)}</td>
                  <td>
                    <div className="flex items-center gap-2">
                      <div className="h-2 bg-blue-500 rounded" style={{ width: `${e.weight_of_book * 120}px` }} />
                      {(e.weight_of_book * 100).toFixed(1)}%
                    </div>
                  </td>
                  <td>{(e.weight_of_equity * 100).toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* Order ticket */}
      <section className="mt-8 border rounded p-4">
        <h2 className="text-lg font-medium">{t("paper.orderTicket")}</h2>
        <div className="mt-3 flex flex-wrap gap-3 items-end">
          <label className="text-sm">
            {t("paper.symbol")}
            <input
              className="border rounded px-2 py-1 block w-28 uppercase"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
            />
          </label>
          <label className="text-sm">
            {t("paper.side")}
            <select
              className="border rounded px-2 py-1 block"
              value={side}
              onChange={(e) => setSide(e.target.value as "buy" | "sell")}
            >
              <option value="buy">{t("paper.buy")}</option>
              <option value="sell">{t("paper.sell")}</option>
            </select>
          </label>
          <label className="text-sm">
            {t("paper.type")}
            <select
              className="border rounded px-2 py-1 block"
              value={orderType}
              onChange={(e) => setOrderType(e.target.value as "market" | "limit" | "stop")}
            >
              <option value="market">{t("paper.market")}</option>
              <option value="limit">{t("paper.limit")}</option>
              <option value="stop">{t("paper.stop")}</option>
            </select>
          </label>
          <label className="text-sm">
            {t("paper.quantity")}
            <input
              type="number"
              min={1}
              className="border rounded px-2 py-1 block w-24"
              value={quantity}
              onChange={(e) => setQuantity(Number(e.target.value))}
            />
          </label>
          {orderType !== "market" && (
            <label className="text-sm">
              {orderType === "limit" ? t("paper.limitPrice") : t("paper.stopPrice")}
              <input
                type="number"
                min={0}
                step="0.01"
                className="border rounded px-2 py-1 block w-28"
                value={limitPrice}
                onChange={(e) => setLimitPrice(Number(e.target.value))}
              />
            </label>
          )}
          <button
            className={`border rounded px-4 py-1 text-white ${side === "buy" ? "bg-green-700" : "bg-red-700"}`}
            onClick={submitOrder}
          >
            {side === "buy" ? t("paper.buy") : t("paper.sell")}
          </button>
        </div>
        {status && <p className="mt-3 text-sm text-gray-600">{status}</p>}
      </section>

      {/* Positions */}
      <section className="mt-8">
        <h2 className="text-lg font-medium">{t("paper.positions")}</h2>
        {snapshot && snapshot.positions.length > 0 ? (
          <table className="mt-3 w-full text-sm border-collapse">
            <thead>
              <tr className="text-left border-b">
                <th className="py-1">{t("paper.symbol")}</th>
                <th>{t("paper.qty")}</th>
                <th>{t("paper.avgCost")}</th>
                <th>{t("paper.lastPrice")}</th>
                <th>{t("paper.marketValue")}</th>
                <th>{t("paper.unrealizedPnl")}</th>
                <th>%</th>
              </tr>
            </thead>
            <tbody>
              {snapshot.positions.map((p) => (
                <tr key={p.symbol} className="border-b">
                  <td className="py-1 font-medium">{p.symbol}</td>
                  <td>{p.quantity}</td>
                  <td>{money(p.avg_cost)}</td>
                  <td>{money(p.last_price)}</td>
                  <td>{money(p.market_value)}</td>
                  <td className={pnlColor(p.unrealized_pnl)}>{money(p.unrealized_pnl)}</td>
                  <td className={pnlColor(p.unrealized_pnl_pct)}>{p.unrealized_pnl_pct.toFixed(2)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="mt-2 text-sm text-gray-500">{t("paper.noPositions")}</p>
        )}
      </section>

      {/* Order history */}
      <section className="mt-8">
        <h2 className="text-lg font-medium">{t("paper.orderHistory")}</h2>
        {orders.length > 0 ? (
          <table className="mt-3 w-full text-sm border-collapse">
            <thead>
              <tr className="text-left border-b">
                <th className="py-1">#</th>
                <th>{t("paper.symbol")}</th>
                <th>{t("paper.side")}</th>
                <th>{t("paper.type")}</th>
                <th>{t("paper.qty")}</th>
                <th>{t("paper.status")}</th>
                <th>{t("paper.fill")}</th>
                <th>{t("paper.note")}</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.id} className="border-b">
                  <td className="py-1">{o.id}</td>
                  <td>{o.symbol}</td>
                  <td className={o.side === "buy" ? "text-green-700" : "text-red-700"}>{t(`paper.${o.side}`)}</td>
                  <td>
                    {t(`paper.${o.order_type}`)}
                    {o.limit_price != null ? ` @ ${money(o.limit_price)}` : ""}
                  </td>
                  <td>{o.quantity}</td>
                  <td className={o.status === "filled" ? "text-green-600" : "text-red-600"}>{t(`paper.status.${o.status}`)}</td>
                  <td>{o.fill_price != null ? money(o.fill_price) : "—"}</td>
                  <td className="text-gray-500">{o.reason ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="mt-2 text-sm text-gray-500">{t("paper.noOrders")}</p>
        )}
      </section>
    </main>
  );
}

function Stat({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div className="border rounded p-3">
      <div className="text-xs text-gray-500">{label}</div>
      <div className={`text-lg font-medium ${className ?? ""}`}>{value}</div>
    </div>
  );
}
