import { INVESTMENT_VIEWS, type InvestmentView } from "@/lib/invest-navigation";
import { Card, secondaryButtonClass } from "./ui";

const sections = [
  ["practice", "第一课"], ["evidence", "读数据与写证据"], ["first-run", "完整流程"],
  ["basics", "炒股基础"], ["pages", "页面地图"], ["advanced", "进阶工具"],
  ["data", "数据与常见问题"],
] as const;

const exercises: { view: InvestmentView; title: string; instructions: string; check: string }[] = [
  {
    view: "watchlist",
    title: "看懂一家公司的一根日K线",
    instructions: "在「按代码加入A股观察池」输入 600519，等名称与报价出现。点「加入观察池」，然后点「查看K线」。选「1个月」，从图上方读出最近一根K线的开盘、最高、最低和收盘价。在电脑上可把鼠标移到其他K线，或聚焦图表后用左右方向键切换。这个代码仅用于演示操作。若已在跟踪该公司，可以选用已有记录。",
    check: "可以指出K线对应的交易日及四个价格，并区分图表截至日期与最新报价时间。历史K线上的收盘价与当前报价使用的时间和复权口径可能不同。",
  },
  {
    view: "tools",
    title: "先算损失，再谈仓位",
    instructions: "在「仓位冲击模拟器」把「单只股票仓位」调到 10%，把「个股下跌幅度」调到 20%。记下「组合损失」，再把仓位改到 5%，保持下跌幅度不变。练习只用滑块，保留驾驶舱里的个人资产数据。",
    check: "组合损失从 2% 变成 1%。如果当前资产为 10 万元，亏损金额从 2,000 元变成 1,000 元。计算假设其他资产和现金的价值不变。",
  },
  {
    view: "journal",
    title: "留下第一条零资金的观察记录",
    instructions: "在「决策复盘」打开记录表单，填写刚才观察的股票代码，动作选择「观察」，金额留空。在「决策理由」写下你想查证的问题，在「支持证据」记录来源和日期，在「退出/失效条件」写下什么情况会让你停止跟踪。点「保存原始决策」。",
    check: "决策时间线出现一条标为「观察」「未涉及资金」的记录。复核时先回答当初的问题有没有新证据，再考虑是否调整观察计划。",
  },
];

const steps: { view: InvestmentView; title: string; text: string }[] = [
  { view: "dashboard", title: "核对资金与回撤防线", text: "核对当前资产、资产峰值、每月新增资金和回撤上限。初始配置是示例。实际持仓和资金仍需手动记录或通过本地快照导入。" },
  { view: "market", title: "读市场雷达", text: "先看沪深300ETF日K线和市场证据，读清楚缺失项。主线候选只用于缩小观察范围，盘中结果可能变化。" },
  { view: "dividends", title: "从红利看板发现候选", text: "先核对扫描样本、日期、分红口径和风险标签，再打开一家公司查看筛选摘要和K线。用「加入观察池」开始跟踪。" },
  { view: "watchlist", title: "在观察池跟踪一家公司", text: "知道股票代码时，可直接输入六位代码。公司名称和行情自动识别，缺失数据会标明。点击公司看K线，再打开个股研究。" },
  { view: "research", title: "写下研究假设", text: "用自己的话写公司靠什么赚钱、有哪些证据和反方观点。保存研究区间并写下失效条件，两者会回到观察池的同一份档案。" },
  { view: "tools", title: "用模拟工具先算一遍", text: "拖动仓位，看股价下跌如何影响总资产。再调整利润增速、估值倍数和分红率，比较三种假设的结果。" },
  { view: "journal", title: "在决策复盘留下记录", text: "记下当时看到的证据、自己的选择、风险和退出条件。之后回看哪些假设成立，哪些地方需要修正。决定暂不行动也可以记录。" },
];

const basics = [
  ["股票与ETF", "股票代表对一家公司的部分所有权。ETF是可在交易所买卖的基金。一只跟踪指数的ETF通常持有一篮子证券。ETF成交价与基金净值可能不同，成交价高于参考价值称为溢价。"],
  ["K线与均线", "一根日K线展示一天的开盘、最高、最低和收盘价。成交量反映交易活跃度，均线反映过去若干交易日收盘价的平均水平。读图时留意时间区间、复权口径和截至日期。"],
  ["市盈率与股息率", "市盈率可理解为股价除以每股盈利。亏损或盈利异常时，比较市盈率容易失真。历史股息率反映特定期间已核实分红与参考股价的比值，未来分红取决于公司决定及其经营情况。"],
  ["仓位与回撤", "假设总资产10万元，一只股票占10%。若它下跌20%，其他资产和现金均不变，总资产约下跌2%。若资产曾到10万元，现在是9万元，从该峰值算起的回撤是10%。"],
  ["A股常见交易约束", "普通A股当天买入通常要到下一交易日才能卖出。部分ETF允许当日回转，交易规则按品种核对。涨跌停时可能有报价但难以成交，实际还受流动性、排队、费用和滑点影响。"],
];

const pageRoles = [
  ["新手指南", "查术语、操作顺序、数据口径和页面分工。"],
  ["A股驾驶舱", "维护自己的资金、持仓、目标配置和回撤预算。"],
  ["市场雷达", "看宽基趋势、市场证据、风险提示与板块候选。"],
  ["情绪周期", "用今日作战、分时监控、周期复盘、回测验证和设置与说明，研究短线情绪与龙头信号。"],
  ["红利看板", "扫描分红样本，看股息、行业分类与价格位置，发现候选。"],
  ["A股观察池", "跟踪候选、最新行情、研究区间、失效条件和待办。"],
  ["个股研究", "编辑公司的论证、证据、估值假设和失效条件。"],
  ["模拟工具", "比较单股下跌的仓位冲击，以及不同估值假设。"],
  ["决策复盘", "记录某一天的决策与证据，便于事后回看。"],
  ["功能中心", "查询行情、基金、筛选因子，运行独立研究工具。"],
];

const toolRoles = [
  ["A股行情 / 综合研究 · 股票诊断", "前者快速看行情、成交量、资金流与新闻。后者做技术和风险诊断，可保存分析快照。"],
  ["多因子选股 / 红利看板", "多因子以动量、趋势、回撤和资金维度筛选。红利看板关注已核实分红与价格位置。"],
  ["基金与ETF / 综合研究 · 基金深研", "前者快速查净值、折溢价和风险，后者做进一步分析并留档。"],
  ["策略回测 / A股策略实验", "两者比较同一组四类策略。前者读已入库日线，后者按需请求供应商日线，比较结果前先核对样本与截至日期。"],
  ["模拟交易 / 综合研究 · 组合推演", "前者维护虚拟账户和订单，后者按假设生成长期组合路径。虚拟订单与实盘持仓分开。"],
  ["AI研究 / 综合研究 · 股票诊断", "前者生成一次性笔记，后者可围绕报告连续追问。两处生成内容都需要核对原始证据。"],
  ["综合研究 · 分析档案 / 决策复盘", "前者保存分析快照与对话，后者保存自己的决策与教训。"],
  ["股债趋势", "并列查看沪深300ETF与国债ETF趋势，补充市场雷达的宽基视角。"],
  ["系统设置 / 综合研究 · 模型与通知", "前者管理主系统DeepSeek与数据设置，后者管理研究实验室的模型与通知。"],
  ["旧合规问答", "历史模块，使用美国市场规则。查A股规则请使用下方交易所资料。"],
];

export default function GuidePanel({ onNavigate }: { onNavigate: (view: InvestmentView) => void }) {
  return (
    <article className="space-y-5">
      <header className="rounded-[22px] border border-emerald-200 bg-emerald-50 p-5 sm:p-8">
        <p className="text-sm font-semibold text-emerald-800">Quant Copilot 使用手册</p>
        <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">新手指南</h2>
        <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-700">第一次接触股票，可以从三件事开始：读懂一根日K线、算清一笔假设亏损、记下一条观察。三项练习均无需实盘交易。遇到陌生术语时，可以随时跳到「炒股基础」。</p>
        <a className={`${secondaryButtonClass} mt-4 inline-block`} href="#practice">开始第一课</a>
      </header>

      <div className="grid items-start gap-5 md:grid-cols-[12rem_minmax(0,1fr)]">
        <aside className="md:sticky md:top-5 md:max-h-[calc(100dvh-2.5rem)] md:overflow-y-auto">
          <Card>
            <nav id="guide-contents" aria-labelledby="guide-contents-title" className="scroll-mt-6">
              <h3 id="guide-contents-title" className="text-lg font-semibold">目录</h3>
              <ol className="mt-3 grid gap-x-8 sm:grid-cols-2 md:grid-cols-1">
                {sections.map(([id, label], index) => (
                  <li className="border-b border-slate-100" key={id}>
                    <a className="flex items-baseline gap-3 rounded-md px-2 py-2 text-sm font-medium text-emerald-900 hover:bg-emerald-50 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-700" href={`#${id}`}>
                      <span aria-hidden="true" className="text-xs tabular-nums text-slate-500">{String(index + 1).padStart(2, "0")}</span>
                      {label}
                    </a>
                  </li>
                ))}
              </ol>
            </nav>
          </Card>
        </aside>

        <div className="min-w-0 space-y-5">
          <section id="practice" className="scroll-mt-6">
            <Card>
              <h3 className="text-xl font-semibold">第一课 · 从看图到记一条观察</h3>
              <p className="mt-2 text-sm leading-7 text-slate-600">跟着做三步即可。观察池和复盘记录会保存在当前浏览器，模拟滑块只改变这次计算。</p>
              <ol className="mt-4 space-y-3">
                {exercises.map((exercise, index) => (
                  <li key={exercise.view} className="rounded-2xl border border-slate-200 p-4 sm:p-5">
                    <p className="text-xs font-semibold text-emerald-800">练习 {index + 1}</p>
                    <h4 className="mt-1 font-semibold">{exercise.title}</h4>
                    <p className="mt-2 text-sm leading-7 text-slate-700">{exercise.instructions}</p>
                    <details className="mt-3 rounded-xl bg-emerald-50 px-3 py-2 text-sm">
                      <summary className="cursor-pointer font-medium text-emerald-900">查看自检答案</summary>
                      <p className="mt-2 leading-6 text-slate-700">{exercise.check}</p>
                    </details>
                    <button className={`${secondaryButtonClass} mt-3`} onClick={() => onNavigate(exercise.view)}>前往{INVESTMENT_VIEWS.find(({ id }) => id === exercise.view)?.label}</button>
                  </li>
                ))}
              </ol>
            </Card>
          </section>

          <section id="evidence" className="scroll-mt-6">
            <Card>
              <h3 className="text-xl font-semibold">读数据与写证据</h3>
              <dl className="mt-3 divide-y divide-slate-100 text-sm leading-7 text-slate-700">
                <div className="py-3"><dt className="font-semibold">先看数据是什么时候的</dt><dd>报价时间代表供应商行情时点，获取时间代表系统何时读到它。休市时，即使获取时间刚更新，价格仍可能来自上一交易日。把两个时间与K线的截至日期分别看。</dd></div>
                <div className="py-3"><dt className="font-semibold">把事实、筛选结果和假设分开</dt><dd>日K线和已实施分红属于可核对的数据。「板块启动」是本系统阈值算出的标签。你写的研究区间和估值情景是个人假设。若看到「不满足」，表示有数据但没达到阈值；「未知」表示无法判断。</dd></div>
                <div className="py-3"><dt className="font-semibold">证据要能查回来</dt><dd>在个股研究里记录公告名称、日期、原文位置和支持判断的具体数字。写下哪些资料还没查到。看到新公告时先核对口径，再回到决策时间线对照当时的理由。</dd></div>
              </dl>
              <details className="mt-3 rounded-xl bg-emerald-50 p-4 text-sm leading-7 text-slate-700">
                <summary className="cursor-pointer font-semibold text-emerald-900">看一个填写示例</summary>
                <p className="mt-2">以下为假设练习。你在红利看板看到某家公司历史股息率较高，想核实这笔分红是否有一次性因素。</p>
                <dl className="mt-2 space-y-1">
                  <div><dt className="inline font-semibold">观察理由 </dt><dd className="inline">核实高股息来自常规分红还是一次性分红。</dd></div>
                  <div><dt className="inline font-semibold">支持证据 </dt><dd className="inline">已看到历史派息记录，待核对分红实施公告和年报现金流。</dd></div>
                  <div><dt className="inline font-semibold">失效条件 </dt><dd className="inline">如果公告确认大部分派息属于一次性分红，就放弃用这次派息估计未来分红。</dd></div>
                  <div><dt className="inline font-semibold">下次复核 </dt><dd className="inline">读完公告后，记录哪些判断仍成立、哪些需要改。下次复盘用新证据和原记录对照。</dd></div>
                </dl>
              </details>
            </Card>
          </section>

          <section id="first-run" className="scroll-mt-6">
            <Card>
              <h3 className="text-xl font-semibold">完整流程 · 从资金到复盘</h3>
              <ol className="mt-4 grid gap-3 sm:grid-cols-2">
                {steps.map((step, index) => <li key={step.view} className="rounded-2xl border border-slate-200 p-4">
                  <p className="text-xs font-semibold text-emerald-800">步骤 {index + 1}</p>
                  <h4 className="mt-1 font-semibold">{step.title}</h4>
                  <p className="my-2 text-sm leading-6 text-slate-600">{step.text}</p>
                  <button className={secondaryButtonClass} onClick={() => onNavigate(step.view)}>打开{INVESTMENT_VIEWS.find(({ id }) => id === step.view)?.label}</button>
                </li>)}
              </ol>
            </Card>
          </section>

          <section id="basics" className="scroll-mt-6">
            <Card>
              <h3 className="text-xl font-semibold">炒股基础</h3>
              <dl className="mt-4 divide-y divide-slate-100">
                {basics.map(([term, definition]) => <div className="py-3" key={term}><dt className="font-semibold">{term}</dt><dd className="mt-1 text-sm leading-7 text-slate-600">{definition}</dd></div>)}
              </dl>
              <div className="flex flex-wrap gap-4 border-t border-slate-100 pt-4 text-sm text-emerald-800 underline underline-offset-4">
                <a href="https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml" target="_blank" rel="noreferrer">上交所交易规则</a>
                <a href="https://www.sse.com.cn/assortment/fund/etf/question/" target="_blank" rel="noreferrer">上交所ETF问答</a>
                <a href="https://investor.szse.cn/warning/activities/fundIntroduction/t20210122_584364.html" target="_blank" rel="noreferrer">深交所基金风险说明</a>
              </div>
            </Card>
          </section>

          {([["pages", "页面地图", pageRoles], ["advanced", "进阶工具", toolRoles]] as const).map(([id, title, rows]) => (
            <section id={id} className="scroll-mt-6" key={id}>
              <Card>
                <h3 className="text-xl font-semibold">{title}</h3>
                <dl className="mt-3 divide-y divide-slate-100">
                  {rows.map(([label, purpose]) => <div className="grid gap-1 py-3 text-sm sm:grid-cols-[minmax(0,1fr)_2fr] sm:gap-5" key={label}><dt className="font-semibold">{label}</dt><dd className="leading-6 text-slate-600">{purpose}</dd></div>)}
                </dl>
              </Card>
            </section>
          ))}

          <section id="data" className="scroll-mt-6">
            <Card>
              <h3 className="text-xl font-semibold">数据与常见问题</h3>
              <dl className="mt-3 space-y-4 text-sm leading-7 text-slate-600">
                <div><dt className="font-semibold text-slate-900">输入代码后为什么还不能加入？</dt><dd>先确认输入的是六位A股股票代码，并保留开头的0。等待识别完成再操作。若显示「打开已有记录」，直接打开原档案。若只有部分数据缺失，以页面标注为准。</dd></div>
                <div><dt className="font-semibold text-slate-900">情绪周期的「板块启动」怎么看？</dt><dd>系统同时检查板块涨幅、匹配到的涨停股数量和最早首次涨停时间。具体阈值在情绪周期的「设置与说明」中查看。三项都满足才标为启动。真实行情中，时间取该行业在涨停池中匹配到的股票的最早首次涨停时间。没有匹配或缺少时间时会显示「未知」。</dd></div>
                <div><dt className="font-semibold text-slate-900">为什么看到几个不同的日期？</dt><dd>公开行情有供应商时间和本机获取时间，休市时通常显示最近报价。日K线有自己的截至交易日，红利列表有扫描快照日期。查看公司详情时以各指标旁的来源、日期与口径为准。缺失值或延迟未知要保留为未知。</dd></div>
                <div><dt className="font-semibold text-slate-900">回撤预警怎么算？</dt><dd>驾驶舱与市场雷达共用当前资产、资产峰值和回撤上限。预警点是上限的50%、75%、90%和100%。上限20%时对应10%、15%、18%和20%。出入金会改变资产口径，更新资产与峰值时要一起核对。价格跳空等情况可能直接越过预警线。</dd></div>
                <div><dt className="font-semibold text-slate-900">公司笔记保存在哪里？</dt><dd>驾驶舱、公司档案和决策复盘保存在当前浏览器。同一股票代码只用一份公司档案，移出观察池后仍可在个股研究找到笔记。清理网站数据或换浏览器可能看不到原记录。情绪周期人工确认独立保存，综合研究档案和模拟账户保存在本地后端。</dd></div>
                <div><dt className="font-semibold text-slate-900">系统能同步券商或下单吗？</dt><dd>当前支持手动维护和本地券商快照导入。公开行情会更新，真实账户的资金、持仓和成交仍以券商为准。模拟交易使用虚拟账户，实际成交约束只在相应工具支持时纳入。</dd></div>
                <div><dt className="font-semibold text-slate-900">模拟数据、真实行情和AI怎么看？</dt><dd>情绪周期的真实入口展示已采集行情和快照，真实历史回测仍受数据覆盖限制。CSV结果依赖导入数据，演示数据用于熟悉界面。估值和组合推演随假设变化，AI输出属于待核实分析。历史统计不代表未来，结果仅供研究。</dd></div>
              </dl>
            </Card>
          </section>
          <a className="inline-block rounded-md px-2 py-2 text-sm font-medium text-emerald-800 underline underline-offset-4 md:hidden" href="#guide-contents">返回目录</a>
        </div>
      </div>
    </article>
  );
}
