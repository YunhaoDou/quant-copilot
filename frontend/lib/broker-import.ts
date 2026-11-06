import type { Holding } from "./personal-investment";

// 仅解析用户选择的本地文件，不读取交易客户端、密码或验证码。
export function parseBrokerCSV(text: string, broker: string): Holding[] {
  text = text.replace(/^\uFEFF/, "");
  const delimiter = text.split(/\r?\n/)[0].includes("\t") ? "\t" : ",";
  const rows: string[][] = []; let row: string[] = [], cell = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === '"') { if (quoted && text[i+1] === '"') { cell += '"'; i++; } else quoted = !quoted; }
    else if (!quoted && ch === delimiter) { row.push(cell.trim()); cell = ""; }
    else if (!quoted && ch === "\n") { row.push(cell.trim()); if (row.some(Boolean)) rows.push(row); row = []; cell = ""; }
    else if (ch !== "\r" || quoted) cell += ch;
  }
  if (quoted) throw new Error("CSV引号未闭合");
  row.push(cell.trim()); if (row.some(Boolean)) rows.push(row);
  const headers = rows.shift() || [];
  const field = (...names: string[]) => headers.findIndex(h => names.includes(h.replace(/\s/g, "")));
  const code = field("证券代码", "股票代码", "代码"), name = field("证券名称", "股票名称", "名称"), qty = field("股票余额", "证券数量", "持仓数量", "当前持仓", "股份余额", "数量"), unitCost = field("成本价", "摊薄成本价", "持仓成本价"), totalCost = field("成本金额", "持仓成本"), value = field("市值", "最新市值", "证券市值", "参考市值"), last = field("最新价", "当前价", "市价");
  if ([code, name, qty].some(n => n < 0) || (unitCost < 0 && totalCost < 0)) throw new Error("需要列：证券代码、证券名称、持仓数量，以及成本价或成本金额。支持同花顺逗号/制表符导出。");
  const seen = new Set<string>();
  function numeric(value: string | undefined, line: number) {
    const n = Number((value ?? "").replace(/,/g, ""));
    if (value == null || !value.trim() || !Number.isFinite(n)) throw new Error(`第${line}行存在无效数字`);
    return n;
  }
  return rows.map((r, i) => {
    const symbol = r[code]?.replace(/^[='"]+|['"]+$/g, "").trim();
    if (!/^\d{6}$/.test(symbol || "")) throw new Error(`第${i+2}行证券代码必须为六位数字`);
    if (seen.has(symbol)) throw new Error(`同一文件存在重复代码${symbol}，请先合并同账户同证券持仓`); seen.add(symbol);
    const quantity = numeric(r[qty], i+2);
    if (quantity < 0 || !Number.isInteger(quantity)) throw new Error(`第${i+2}行持仓数量必须为非负整数`);
    const cost = totalCost >= 0 ? numeric(r[totalCost], i+2) : numeric(r[unitCost], i+2)*quantity;
    const marketValue = value >= 0 ? numeric(r[value], i+2) : last >= 0 ? numeric(r[last], i+2)*quantity : 0;
    return { id: `broker-${broker}-${symbol}`, code: symbol, name: r[name], quantity, broker, importedAt: new Date().toISOString(), cost, marketValue, thesis: "券商导出快照；行情估值由独立报价更新" };
  }).filter(r => (r.quantity || 0) > 0);
}
