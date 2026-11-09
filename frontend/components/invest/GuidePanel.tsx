import { INVESTMENT_VIEWS, type InvestmentView } from "@/lib/invest-navigation";
import { Card, secondaryButtonClass } from "./ui";

const sections = [
  ["start", "启动系统"], ["practice", "第一课"], ["first-run", "完整流程"],
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
        <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-700">第一次接触股票，可以先读基础术语，再走一遍从观察到复盘的流程。系统用于行情观察、记录、研究和模拟，任何一步都可以在没有实盘交易的情况下完成。</p>
        <nav aria-label="指南目录" className="mt-5 flex flex-wrap gap-2">
          {sections.map(([id, label]) => <a className={secondaryButtonClass} href={`#${id}`} key={id}>{label}</a>)}
        </nav>
      </header>

      <section id="start" className="scroll-mt-6">
        <Card>
          <h3 className="text-xl font-semibold">启动系统</h3>
          <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm leading-7 text-slate-700">
            <li>在已安装启动器的 Mac 上按 <kbd className="rounded border bg-slate-50 px-1.5 py-0.5">⌘ 空格</kbd>，输入 <strong>Quant Copilot</strong>，按回车。</li>
            <li>等待默认浏览器打开「A股驾驶舱」。已经启动时，也可以直接打开浏览器收藏的驾驶舱。</li>
            <li>第一次练习可以保留原有账户数据，从观察一家公司和拖动模拟滑块开始。</li>
          </ol>
          <a className={`${secondaryButtonClass} mt-4 inline-block`} href="#practice">开始第一课</a>
        </Card>
      </section>

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
            <div><dt className="font-semibold text-slate-900">Spotlight 找不到应用，或打开后浏览器没出现怎么办？</dt><dd>先在 Finder 的个人「应用程序」文件夹确认 Quant Copilot.app 是否存在。若启动器显示错误，按提示查看启动日志。如果浏览器能打开，但多处行情同时加载失败，可以访问 <a className="font-medium text-emerald-800 underline" href="http://localhost:8000/health" target="_blank" rel="noreferrer">本地后端状态</a>。后端有响应时，再查看行情卡的供应商状态和报价时间。</dd></div>
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
    </article>
  );
}
