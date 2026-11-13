"use client";
import { useState } from "react";
import {useVisiblePoll} from "@/lib/read-resource";
import { marketApiUrl } from "@/lib/live-market";
import { accountRulesSuffix, accountStatusText, formatAccountTime, toAccountView, type TradeView } from "@/lib/account-view";
import { Card, buttonClass, secondaryButtonClass } from "./ui";
import PaperAccountCard from "./PaperAccountCard";
import TradeTable from "./TradeTable";

type Account = {
  status: string; created_at: string; capital: number; cash: number; equity: number; peak: number;
  position: { name: string; symbol: string; quantity: number; entry_price: number; mark: number; mark_time: string } | null;
  pending: { side: string; symbol: string; reason: string; signal_time: string } | null;
  rules: Record<string, number>;
  inception_date?: string;
  decisions: { time: string; text: string; event_id: string | null }[];
  trades: { time: string; side: string; symbol: string; quantity: number; price: number; pnl: number | null; reason: string }[];
};
const stamp = formatAccountTime;

export default function CycleStrategySimulation() {
  const [account, setAccount] = useState<Account | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [reviews, setReviews] = useState<{ trade_date: string; reviewed_at: string; mode: string; action: string; reason: string; source: string; window: number; previous_low: number; previous_low_date: string; today_low: number; today_close: number; previous_close_low: number }[]>([]);
  async function load(action = "", signal?: AbortSignal) {
    try {
      const response = await fetch(`${marketApiUrl()}/cycle/strategy-sim${action}`, { method: action ? "POST" : "GET", cache: "no-store", signal });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "读取模拟账户失败");
      setAccount(data.account); setError("");
      if (Array.isArray(data.reviews)) setReviews(data.reviews);
    } catch (e) { if (!signal?.aborted) setError(String(e)); }
  }
  useVisiblePoll(signal=>load("",signal),30000);
  async function control(action: string) {
    setBusy(true); await load(action); setBusy(false);
  }
  const view = toAccountView(account);
  const trades: TradeView[] | undefined = account?.trades.map((trade) => ({
    time: stamp(trade.time), symbol: trade.symbol, side: trade.side, price: trade.price,
    quantity: trade.quantity, pnl: trade.pnl, reason: trade.reason,
  }));
  return <div className="space-y-5">
    <Card><div className="flex flex-wrap justify-between gap-3">
      <div><h3 className="text-xl font-semibold">启动—分歧—回补 · 策略模拟</h3><p className="mt-2 text-sm leading-7 text-slate-600">后台根据事件证据管理独立虚拟账户，记录等待、信号及后续报价撮合。账户、持仓和流水保存在本地后端。</p></div>
      <div className="flex flex-wrap gap-2">
        <button className={secondaryButtonClass} onClick={() => load()}>刷新模拟账户</button>
        <button disabled={busy} className={secondaryButtonClass} onClick={async () => {
          setBusy(true);
          try {
            const response = await fetch(`${marketApiUrl()}/cycle/strategy-sim/review-today`, { method: "POST" });
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || "核验失败");
            await load();
          } catch (e) { setError(String(e)); } finally { setBusy(false); }
        }}>核验今日机会</button>
      </div>
    </div>{error && <p role="alert" className="mt-3 text-red-700">{error}</p>}</Card>
    <Card><h4 className="font-semibold">本轮规则与假设</h4><ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-7 text-slate-700">
      <li>首次事件必须有大盘新低证据，且事件人工阶段已确认启动或回补。缺少这些依据时持续等待，并写明原因。</li>
      <li>启动后第1至2个已采集交易日期观察板块候选首位；第3个采集日期采取减险退出；第4个采集日期仅在人工确认回补后再观察进入，第5个采集日期退出。这是待检验的时间假设，采集缺口会影响日期计数。</li>
      <li>模拟信号最早使用下一可得报价撮合。采用T+1，涨停买单及跌停卖单等待，风险警示或价格字段不足时不成交。公开报价无法还原盘口排队与真实成交量，结果需结合成交记录评价。</li>
      <li>默认本金10万元、单仓10%、价格止损8%、止盈15%、组合回撤防线20%。费用与滑点读取项目配置。首版同时持有一只股票，每事件每阶段最多进入一次。</li>
      <li>冰点逆势连板、电风扇轮动及盘中洗盘意图仍需证据化定义。当前自动模拟聚焦启动、人工确认的回补及风险退出。</li>
    </ul></Card>
    {reviews.map(review => <Card key={review.trade_date}>
      <h4 className="font-semibold">{review.trade_date} · {review.mode} · {review.action}</h4>
      <p className="mt-2 text-sm leading-7">{review.reason}</p>
      <p className="mt-2 text-sm leading-7">今日最低 {review.today_low.toFixed(2)} · 前{review.window}交易日最低 {review.previous_low.toFixed(2)}（{review.previous_low_date}）</p>
      <p className="text-sm leading-7">今日收盘参考 {review.today_close.toFixed(2)} · 前置窗口最低收盘 {review.previous_close_low.toFixed(2)}</p>
      <p className="mt-2 text-xs text-slate-500">{review.source} · 核验 {stamp(review.reviewed_at)} · 此记录为独立核验结果</p>
    </Card>)}
    <PaperAccountCard
      title={`模拟账户 · ${accountStatusText(view)}`}
      account={view}
      busy={busy}
      actions={[
        { id: "start", label: account ? "继续模拟" : "启动模拟", primary: true, onClick: () => control("/start"), disabled: view?.status === "running" },
        { id: "pause", label: "暂停模拟", onClick: () => control("/pause"), disabled: view?.status !== "running" },
        { id: "exit", label: "请求模拟退出", onClick: () => control("/exit"), disabled: !account?.position && !account?.pending },
      ]}
      meta={account && <>
        <p className="mt-3 text-xs text-slate-500">启动 {stamp(account.created_at)}{accountRulesSuffix(account.rules)}</p>
        {account.inception_date && <p className="mt-2 text-xs text-slate-500">模拟执行起始日 {account.inception_date} · 起始日回溯结果见判断日志</p>}
      </>}
      position={account && <p className="mt-3 text-sm">{account.position ? `${account.position.name} ${account.position.symbol} · ${account.position.quantity}股 · 入场 ${account.position.entry_price.toFixed(3)} · 参考价 ${account.position.mark.toFixed(3)} · ${stamp(account.position.mark_time)}` : "当前无模拟持仓"}</p>}
      pending={account?.pending && <p className="mt-2 text-sm text-amber-800">待处理模拟{account.pending.side === "buy" ? "买单" : "卖单"} · {account.pending.symbol} · {account.pending.reason}</p>}
    />
    {account && <>
      <Card><h4 className="font-semibold">策略判断日志</h4><div className="mt-3 max-h-96 overflow-auto">
        {account.decisions.slice().reverse().map((decision, i) => <div className="border-t py-3 text-sm leading-7" key={i}><p className="text-xs text-slate-500">{stamp(decision.time)}</p><p>{decision.text}</p></div>)}
        {!account.decisions.length && <p className="text-sm text-slate-500">等待后台收到启动后的新鲜事件报价。</p>}
      </div></Card>
      <Card><h4 className="font-semibold">模拟成交流水</h4>
        <TradeTable rows={trades} emptyText="尚无模拟成交，请先查看判断日志中的等待条件。" />
      </Card>
    </>}
  </div>;
}
