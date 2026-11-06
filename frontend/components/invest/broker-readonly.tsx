"use client";

import { useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { parseBrokerCSV } from "@/lib/broker-import";
import type { Holding, PersonalInvestmentState } from "@/lib/personal-investment";
import { buttonClass, secondaryButtonClass, Card, Field, inputClass, money } from "./ui";

export default function BrokerReadonly({ state, setState }: { state: PersonalInvestmentState; setState: Dispatch<SetStateAction<PersonalInvestmentState>> }) {
  const [broker, setBroker] = useState("中国银河证券"), [preview, setPreview] = useState<Holding[]>([]), [error, setError] = useState(""), [message, setMessage] = useState("");
  async function load(file?: File) {
    setError(""); setMessage(""); setPreview([]); if (!file) return;
    if (file.size > 2*1024*1024) { setError("文件超过2MB，请只导出资金股票持仓表。"); return; }
    try {
      const bytes = await file.arrayBuffer(); let text = new TextDecoder("utf-8").decode(bytes);
      if (text.includes("�")) text = new TextDecoder("gb18030").decode(bytes);
      const parsed = parseBrokerCSV(text, broker); if (!parsed.length) throw new Error("没有有效持仓记录"); setPreview(parsed);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }
  function apply() {
    if (preview.some(h => h.broker !== broker)) { setError("券商已切换，请重新选择该券商文件。"); return; }
    setState(current => ({ ...current, holdings: [...current.holdings.filter(h => h.broker !== broker), ...preview] }));
    setMessage(`已导入${broker}的${preview.length}项持仓，仅更新本系统；另一个券商及手工持仓保留。`); setPreview([]);
  }
  return <Card><div className="flex flex-wrap justify-between gap-3"><div><h2 className="text-lg font-semibold">券商账户 · 只读数据</h2><p className="mt-1 text-sm text-slate-500">同花顺 / 中国银河证券 / 中信建投证券</p></div><span className="h-fit rounded-full bg-amber-50 px-3 py-1 text-xs text-amber-800">直连未授权 · 支持本地导入</span></div><p className="mt-3 text-xs leading-6 text-slate-500">导入“资金股票/持仓”CSV或制表符文件，先预览再确认。文件只在浏览器解析，不上传文件、不读取客户端登录信息。当前尚无账户API，资金余额与总资产请根据券商快照在个人参数中维护。</p><div className="mt-4 grid gap-3 sm:grid-cols-2"><Field label="券商"><select className={inputClass} value={broker} onChange={e => { setBroker(e.target.value); setPreview([]); setMessage(""); }}><option>中国银河证券</option><option>中信建投证券</option></select></Field><Field label="选择同花顺导出文件"><input type="file" accept=".csv,.txt,.tsv" className={inputClass} onChange={e => load(e.target.files?.[0])} /></Field></div>{error && <p className="mt-3 text-sm text-red-700">{error}</p>}{message && <p className="mt-3 text-sm text-emerald-700">{message}</p>}{preview.length > 0 && <div className="mt-4"><div className="max-h-60 overflow-auto rounded-xl bg-slate-50 p-3">{preview.map(h => <div key={h.id} className="flex flex-wrap justify-between gap-2 border-b py-2 text-xs"><span>{h.code} {h.name}</span><span>{h.quantity}股 · 成本金额{money(h.cost)}</span></div>)}</div><p className="mt-2 text-xs text-amber-700">确认将替换本系统中该券商此前导入的持仓快照。</p><div className="mt-3 flex gap-2"><button className={buttonClass} onClick={apply}>确认导入{preview.length}项持仓</button><button className={secondaryButtonClass} onClick={() => setPreview([])}>取消</button></div></div>}<div className="mt-4 flex flex-wrap gap-2">{["中国银河证券", "中信建投证券"].map(b => <span key={b} className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500">{b}：{state.holdings.filter(h => h.broker === b).length}项已导入</span>)}</div></Card>;
}
