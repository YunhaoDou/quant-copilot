import { useState } from "react";
import type { ViewTarget } from "@/lib/invest-navigation";
import { secondaryButtonClass } from "./ui";

const prices = [
  [10.0, 10.4, 9.8, 10.2, 85], [10.2, 10.8, 10.1, 10.6, 93],
  [10.6, 11.1, 10.5, 10.9, 110], [10.9, 11.6, 10.8, 11.4, 138],
  [11.4, 12.1, 11.3, 12.0, 150], [11.5, 11.6, 10.3, 10.6, 205],
  [10.6, 11.1, 10.5, 10.9, 100], [10.9, 11.4, 10.7, 11.2, 122],
];
const benchmark = [100, 101, 102, 103, 104, 103, 104, 105];
const closes = prices.map((row) => row[3]);
const normalized = closes.map((price) => 100 * price / closes[0]);
const drawdown = closes.map((price, i) => 100 * (price / Math.max(...closes.slice(0, i + 1)) - 1));
const means = closes.map((_, i) => i >= 2 ? (closes[i] + closes[i - 1] + closes[i - 2]) / 3 : null);
const chartTypes = [
  { id: "candle", name: "K线、均线和量能", ticks: [12, 11.5, 11, 10.5, 10], min: 9.7, max: 12.2 },
  { id: "relative", name: "个股与基准", ticks: [118, 112, 106, 100], min: 98, max: 120 },
  { id: "drawdown", name: "从峰值算回撤", ticks: [0, -3, -6, -9, -12], min: -13, max: 0 },
] as const;

export default function GuideCharts({ onNavigate }: { onNavigate: (view: ViewTarget, tab?: string) => void }) {
  const [mode, setMode] = useState(0);
  const [selected, setSelected] = useState(5);
  const chart = chartTypes[mode];
  const [open, high, low, close, volume] = prices[selected];
  const average = means[selected];
  const x = (i: number) => 58 + i * 56;
  const y = (v: number) => 24 + (chart.max - v) * 178 / (chart.max - chart.min);
  const points = (values: (number | null)[]) => values.flatMap((v, i) => v === null ? [] : [`${x(i)},${y(v)}`]).join(" ");
  const pct = (n: number) => `${n.toFixed(2)}%`;

  return (
    <section className="space-y-5">
      <div>
        <h3 className="text-2xl font-semibold text-slate-950">看图入门</h3>
        <p className="mt-2 text-sm leading-7 text-slate-700">以下为八个交易日的虚构数据。先认横轴、纵轴和单位，再选一天读数字，最后看它和前后几天、均线或基准有什么变化。</p>
      </div>
      <div className="flex flex-wrap gap-2" aria-label="图表类型">
        {chartTypes.map(({ id, name }, index) => <button key={id} type="button" aria-pressed={mode === index} className={`${secondaryButtonClass} aria-pressed:bg-emerald-50 aria-pressed:border-emerald-400`} onClick={() => setMode(index)}>{name}</button>)}
      </div>
      <figure className="space-y-2">
        <svg viewBox="0 0 474 270" className="h-auto w-full max-w-3xl" role="img" aria-label={`教学示意图：${chart.name}`}>
          <rect x={x(selected) - 19} y="20" width="38" height="225" fill="#d1fae5" />
          {chart.ticks.map((tick) => <g key={tick}>
            <text x="35" y={y(tick) + 4} textAnchor="end" fontSize="10" fill="#475569">{tick}{mode === 2 ? "%" : ""}</text>
            <line x1="41" y1={y(tick)} x2="465" y2={y(tick)} stroke="#cbd5e1" strokeDasharray="3 4" />
          </g>)}
          {mode === 0 && <>
            {prices.map(([o, h, l, c, v], i) => {
              const color = c >= o ? "#b91c1c" : "#047857";
              return <g key={i}>
                <line x1={x(i)} y1={y(h)} x2={x(i)} y2={y(l)} stroke={color} strokeWidth="2" />
                <rect x={x(i) - 8} y={Math.min(y(o), y(c))} width="16" height={Math.max(2, Math.abs(y(o) - y(c)))} fill={color} />
                <rect x={x(i) - 8} y={245 - v / 7} width="16" height={v / 7} fill={color} opacity="0.75" />
              </g>;
            })}
            <polyline points={points(means)} fill="none" stroke="#2563eb" strokeWidth="2" />
          </>}
          {mode === 1 && <>
            <polyline points={points(normalized)} fill="none" stroke="#047857" strokeWidth="2.5" />
            <polyline points={points(benchmark)} fill="none" stroke="#2563eb" strokeWidth="2.5" strokeDasharray="5 3" />
            <circle cx={x(selected)} cy={y(normalized[selected])} r="4" fill="#047857" />
            <circle cx={x(selected)} cy={y(benchmark[selected])} r="4" fill="#2563eb" />
          </>}
          {mode === 2 && <>
            <polyline points={points(drawdown)} fill="none" stroke="#7c3aed" strokeWidth="2.5" />
            <circle cx={x(selected)} cy={y(drawdown[selected])} r="4" fill="#7c3aed" />
          </>}
          {prices.map((_, i) => <text key={i} x={x(i)} y="264" textAnchor="middle" fontSize="10" fill="#475569">第{i + 1}日</text>)}
        </svg>
        <figcaption className="text-xs leading-6 text-slate-600">
          {mode === 0 ? "纵轴为价格（元）。红色实体表示收盘高于开盘，绿色相反。蓝线为3日均线，底部柱为成交量。" : mode === 1 ? "两条线从100起步。绿实线是个股，蓝虚线是基准，纵轴为归一化值。" : "纵轴为相对此前最高收盘价的百分比。0%表示处于收盘峰值。"}
        </figcaption>
      </figure>
      <div className="flex flex-wrap gap-2" aria-label="查看交易日">
        {prices.map((_, index) => <button key={index} type="button" aria-pressed={selected === index} className={`${secondaryButtonClass} aria-pressed:bg-emerald-50 aria-pressed:border-emerald-400`} onClick={() => setSelected(index)}>第 {index + 1} 日</button>)}
      </div>
      <p role="status" className="text-sm font-medium leading-7 text-slate-800">
        第 {selected + 1} 日 · {mode === 0 ? `开 ${open.toFixed(2)} · 高 ${high.toFixed(2)} · 低 ${low.toFixed(2)} · 收 ${close.toFixed(2)} 元 · 成交量 ${volume} 万股${average === null ? "" : ` · 3日均线 ${average.toFixed(2)} 元`}` : mode === 1 ? `个股累计收益 ${pct(normalized[selected] - 100)} · 基准累计收益 ${pct(benchmark[selected] - 100)} · 相差 ${(normalized[selected] - benchmark[selected]).toFixed(2)} 个百分点` : `收盘 ${close.toFixed(2)} 元 · 相对历史收盘峰值回撤 ${pct(drawdown[selected])}`}
      </p>
      <dl className="divide-y divide-slate-200 text-sm leading-7 text-slate-700">
        <div className="py-3"><dt className="font-semibold text-slate-950">K线和成交量</dt><dd>第6日开11.50元、收10.60元，实体为绿，最高11.60元、最低10.30元对应两端影线。与第5日收盘12.00元相比，开盘跳低0.50元。量柱比前几日高，表明交易更活跃。结合前高、前低和多天收盘位置判断结构，量柱本身无法说明是谁在交易。</dd></div>
        <div className="py-3"><dt className="font-semibold text-slate-950">均线和趋势</dt><dd>第6日的3日均线约11.33元，由第4至6日收盘价平均得到。价格跌到均线下，描述的是当前价格低于近期平均。真实日图里常见20、60、200日均线，周期越长通常越平滑。识别趋势时也看高低点是否连续抬升或降低。</dd></div>
        <div className="py-3"><dt className="font-semibold text-slate-950">相对强弱与回撤</dt><dd>第6日个股仍比起点高3.92%，同时比自身峰值回撤11.67%。两个数字的分母不同。比较个股与基准时，先对齐起点、期间和分红口径。读回测权益曲线时，再核对费用、样本覆盖与成交假设。</dd></div>
        <div className="py-3"><dt className="font-semibold text-slate-950">分时、复权与指标面板</dt><dd>分时横轴按交易时刻，日K按交易日；分时上看跳空、早盘高低点和均价线，先确认是否为完整时段。前复权图适合连贯观察历史走势，实际成交与除权日现金要按原始价格和公告核对。成交量单位、指标周期和图上日期范围都可能改变读法。</dd></div>
      </dl>
      <div className="flex flex-wrap gap-2">
        <button type="button" className={secondaryButtonClass} onClick={() => onNavigate("market")}>去市场雷达看真实K线</button>
        <button type="button" className={secondaryButtonClass} onClick={() => onNavigate("cycle")}>去情绪周期看分时</button>
      </div>
    </section>
  );
}
