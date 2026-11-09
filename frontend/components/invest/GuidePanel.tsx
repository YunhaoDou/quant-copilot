import { useEffect, useState } from "react";

import { INVESTMENT_VIEWS, type InvestmentView } from "@/lib/invest-navigation";
import { Card, secondaryButtonClass } from "./ui";
import { knowledgeChapters } from "./guide-knowledge";
import { projectSections } from "./guide-project";
import { courses } from "./guide-courses";

const guideUrl = "/invest?view=guide";
const progressKey = "quant-copilot-guide-progress-v1";

const courseParts = [
  { id: "concepts", title: "概念讲解" },
  { id: "example", title: "算例" },
  { id: "quiz", title: "课后自测" },
  { id: "reference", title: "知识点速查" },
];
const defaultPart = courseParts[0].id;

type LearningProgress = { completed: string[]; lastVisited: string | null; lastPart?: string };
const emptyProgress: LearningProgress = { completed: [], lastVisited: null };

function readProgress(): LearningProgress {
  const raw = window.localStorage.getItem(progressKey);
  if (!raw) return emptyProgress;
  try {
    const saved = JSON.parse(raw);
    return {
      completed: Array.isArray(saved?.completed) ? courses.filter(({ id }) => saved.completed.includes(id)).map(({ id }) => id) : [],
      lastVisited: courses.find(({ id }) => id === saved?.lastVisited)?.id ?? null,
      lastPart: courseParts.find(({ id }) => id === saved?.lastPart)?.id,
    };
  } catch {
    return emptyProgress;
  }
}

function pageUrl(id: string) {
  return `${guideUrl}&page=${id}`;
}

function courseUrl(id: string, part = defaultPart) {
  return `${guideUrl}&lesson=${id}${part === defaultPart ? "" : `&page=${part}`}`;
}

const directory = [
  { id: "project", title: "项目", entries: [
    { id: "practice", title: "第一课" },
    { id: "evidence", title: "读数据与写证据" },
    ...projectSections,
    { id: "data", title: "数据与常见问题" },
  ] },
  { id: "knowledge", title: "知识", entries: [
    { id: "basics", title: "常用术语" },
    ...courses.map(({ id, title }) => ({ id, title, href: courseUrl(id) })),
    { id: "after-roadmap", title: "D150 之后" },
  ] },
];

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

const basics = [
  ["股票与ETF", "股票代表对一家公司的部分所有权。ETF是可在交易所买卖的基金。一只跟踪指数的ETF通常持有一篮子证券。ETF成交价与基金净值可能不同，成交价高于参考价值称为溢价。"],
  ["K线与均线", "一根日K线展示一天的开盘、最高、最低和收盘价。成交量反映交易活跃度，均线反映过去若干交易日收盘价的平均水平。读图时留意时间区间、复权口径和截至日期。"],
  ["市盈率与股息率", "市盈率可理解为股价除以每股盈利。亏损或盈利异常时，比较市盈率容易失真。历史股息率反映特定期间已核实分红与参考股价的比值，未来分红取决于公司决定及其经营情况。"],
  ["仓位与回撤", "假设总资产10万元，一只股票占10%。若它下跌20%，其他资产和现金均不变，总资产约下跌2%。若资产曾到10万元，现在是9万元，从该峰值算起的回撤是10%。"],
  ["A股常见交易约束", "普通A股当天买入通常要到下一交易日才能卖出。部分ETF允许当日回转，交易规则按品种核对。涨跌停时可能有报价但难以成交，实际还受流动性、排队、费用和滑点影响。"],
];

export default function GuidePanel({ onNavigate, lesson, page }: { onNavigate: (view: InvestmentView) => void; lesson: string | null; page: string | null }) {
  const courseIndex = courses.findIndex(({ id }) => id === lesson);
  const course = courses[courseIndex];
  const courseId = course?.id;
  const part = courseParts.find(({ id }) => id === page)?.id ?? defaultPart;
  const group = directory.find(({ id, entries }) => id === page || entries.some((entry) => entry.id === page)) ?? directory[0];
  const activePage = group.entries.find(({ id }) => id === page)?.id ?? group.id;
  const [progress, setProgress] = useState(emptyProgress);
  const [storageError, setStorageError] = useState(false);

  useEffect(() => {
    function syncProgress(event?: StorageEvent) {
      if (event && event.key !== progressKey && event.key !== null) return;
      try {
        const saved = readProgress();
        const next = !event && courseId && (saved.lastVisited !== courseId || saved.lastPart !== part)
          ? { ...saved, lastVisited: courseId, lastPart: part }
          : saved;
        if (next !== saved) window.localStorage.setItem(progressKey, JSON.stringify(next));
        setProgress(next);
        setStorageError(false);
      } catch {
        setStorageError(true);
      }
    }
    syncProgress();
    window.addEventListener("storage", syncProgress);
    return () => window.removeEventListener("storage", syncProgress);
  }, [courseId, part]);

  function toggleCompletion() {
    if (!courseId) return;
    try {
      const saved = readProgress();
      const completed = saved.completed.includes(courseId)
        ? saved.completed.filter((id) => id !== courseId)
        : [...saved.completed, courseId];
      const next = { ...saved, completed };
      window.localStorage.setItem(progressKey, JSON.stringify(next));
      setProgress(next);
      setStorageError(false);
    } catch {
      setStorageError(true);
    }
  }

  const resume = courses.find(({ id }) => id === progress.lastVisited && !progress.completed.includes(id))
    ?? courses.find(({ id }) => !progress.completed.includes(id));
  return (
    <article className="space-y-5">
      <header className="rounded-[22px] border border-emerald-200 bg-emerald-50 p-5 sm:p-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-semibold text-emerald-800">Quant Copilot 使用手册</p>
            <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">新手指南</h2>
            <p className="mt-2 text-sm leading-7 text-slate-700">{course ? `站内课程 · 第 ${courseIndex + 1} / ${courses.length} 课` : "项目操作与站内金融课程"}</p>
          </div>
          <div className="min-w-[12rem] rounded-xl border border-emerald-200 bg-white/80 p-3 sm:min-w-[15rem]">
            <p className="text-xs font-semibold text-emerald-800">学习进度</p>
            <p className="my-2 text-sm font-medium text-slate-800" role="status">已完成 {progress.completed.length} / {courses.length} 课</p>
            {resume && <a className={secondaryButtonClass} href={courseUrl(resume.id, resume.id === progress.lastVisited ? progress.lastPart : undefined)}>{progress.lastVisited ? "继续学习" : "开始学习"}</a>}
          </div>
        </div>
      </header>

      <div className="grid items-start gap-5 md:grid-cols-[12rem_minmax(0,1fr)]">
        <aside className="md:sticky md:top-5 md:max-h-[calc(100dvh-2.5rem)] md:overflow-y-auto">
          <Card>
            <nav id="guide-contents" aria-labelledby="guide-contents-title" className="scroll-mt-6">
              <h3 id="guide-contents-title" className="text-lg font-semibold">目录</h3>
              <ul className="mt-3 space-y-4">
                {directory.map((group) => (
                  <li key={group.id}>
                    <a className="block rounded-md bg-emerald-50 px-2 py-1.5 text-sm font-semibold text-emerald-900 hover:underline" aria-current={!course && activePage === group.id ? "page" : undefined} href={pageUrl(group.id)}>{group.title}</a>
                    <ul className="mt-1 grid gap-x-3 sm:grid-cols-2 md:grid-cols-1">
                      {group.entries.map((entry) => (
                        <li key={entry.id}>
                          <a className="block rounded-md px-2 py-1.5 text-xs leading-5 text-slate-700 hover:bg-emerald-50 hover:underline aria-[current=page]:bg-emerald-100 aria-[current=page]:font-semibold" aria-current={(course?.id ?? activePage) === entry.id ? "page" : undefined} href={"href" in entry ? entry.href : pageUrl(entry.id)}>{entry.title}</a>
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            </nav>
          </Card>
        </aside>

        <div className="min-w-0 space-y-5 px-1 py-2 md:px-3">
          {storageError && <p role="alert" className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">浏览器存储暂不可用，学习进度无法保存。</p>}
          {course ? <CourseContent index={courseIndex} part={part} completed={progress.completed.includes(course.id)} onToggleCompletion={toggleCompletion} /> : <>
            {activePage === "project" && <section>
              <h3 className="text-xl font-semibold">项目</h3>
              <p className="mt-2 text-sm leading-7 text-slate-700">按功能查操作，也可以从第一课做一遍零资金练习。</p>
              <ul className="mt-3 divide-y divide-slate-200">
                {directory[0].entries.map(({ id, title }) => <li key={id}><a className="block py-3 text-sm font-medium text-emerald-900 hover:underline" href={pageUrl(id)}>{title}</a></li>)}
              </ul>
            </section>}
            {activePage === "practice" && <section id="practice" className="scroll-mt-6">
              <h4 className="text-xl font-semibold">第一课 · 从看图到记一条观察</h4>
              <p className="mt-2 text-sm leading-7 text-slate-600">跟着做三步即可。观察池和复盘记录会保存在当前浏览器，模拟滑块只改变这次计算。</p>
              <ol className="mt-4 divide-y divide-slate-200">
                {exercises.map((exercise, index) => (
                  <li key={exercise.view} className="py-4">
                    <p className="text-xs font-semibold text-emerald-800">练习 {index + 1}</p>
                    <h5 className="mt-1 font-semibold">{exercise.title}</h5>
                    <p className="mt-2 text-sm leading-7 text-slate-700">{exercise.instructions}</p>
                    <details className="mt-3 text-sm">
                      <summary className="cursor-pointer font-medium text-emerald-900">查看自检答案</summary>
                      <p className="mt-2 leading-6 text-slate-700">{exercise.check}</p>
                    </details>
                    <button className={`${secondaryButtonClass} mt-3`} onClick={() => onNavigate(exercise.view)}>前往{INVESTMENT_VIEWS.find(({ id }) => id === exercise.view)?.label}</button>
                  </li>
                ))}
              </ol>
            </section>}

            {activePage === "evidence" && <section id="evidence" className="scroll-mt-6">
              <h4 className="text-xl font-semibold">读数据与写证据</h4>
              <dl className="mt-3 divide-y divide-slate-100 text-sm leading-7 text-slate-700">
                <div className="py-3"><dt className="font-semibold">先看数据是什么时候的</dt><dd>报价时间代表供应商行情时点，获取时间代表系统何时读到它。休市时，即使获取时间刚更新，价格仍可能来自上一交易日。把两个时间与K线的截至日期分别看。</dd></div>
                <div className="py-3"><dt className="font-semibold">把事实、筛选结果和假设分开</dt><dd>日K线和已实施分红属于可核对的数据。「板块启动」是本系统阈值算出的标签。你写的研究区间和估值情景是个人假设。若看到「不满足」，表示有数据但没达到阈值；「未知」表示无法判断。</dd></div>
                <div className="py-3"><dt className="font-semibold">证据要能查回来</dt><dd>在个股研究里记录公告名称、日期、原文位置和支持判断的具体数字。写下哪些资料还没查到。看到新公告时先核对口径，再回到决策时间线对照当时的理由。</dd></div>
              </dl>
              <details className="mt-4 border-t border-slate-200 pt-4 text-sm leading-7 text-slate-700">
                <summary className="cursor-pointer font-semibold text-emerald-900">看一个填写示例</summary>
                <p className="mt-2">以下为假设练习。你在红利看板看到某家公司历史股息率较高，想核实这笔分红是否有一次性因素。</p>
                <dl className="mt-2 space-y-1">
                  <div><dt className="inline font-semibold">观察理由 </dt><dd className="inline">核实高股息来自常规分红还是一次性分红。</dd></div>
                  <div><dt className="inline font-semibold">支持证据 </dt><dd className="inline">已看到历史派息记录，待核对分红实施公告和年报现金流。</dd></div>
                  <div><dt className="inline font-semibold">失效条件 </dt><dd className="inline">如果公告确认大部分派息属于一次性分红，就放弃用这次派息估计未来分红。</dd></div>
                  <div><dt className="inline font-semibold">下次复核 </dt><dd className="inline">读完公告后，记录哪些判断仍成立、哪些需要改。下次复盘用新证据和原记录对照。</dd></div>
                </dl>
              </details>
            </section>}

            {projectSections.filter(({ id }) => id === activePage).map(({ id, title, view, entries }) => (
              <section id={id} className="scroll-mt-6" key={id}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h4 className="text-xl font-semibold">{title}</h4>
                  <button className={secondaryButtonClass} onClick={() => onNavigate(view)}>打开{INVESTMENT_VIEWS.find((item) => item.id === view)?.label}</button>
                </div>
                <dl className="mt-3 divide-y divide-slate-100">
                  {entries.map(([label, instructions]) => (
                    <div className="py-3 text-sm" key={label}>
                      <dt className="font-semibold">{label}</dt>
                      <dd className="mt-1 leading-7 text-slate-700">{instructions}</dd>
                    </div>
                  ))}
                </dl>
              </section>
            ))}

            {activePage === "data" && <section id="data" className="scroll-mt-6">
              <h4 className="text-xl font-semibold">数据与常见问题</h4>
              <dl className="mt-3 space-y-4 text-sm leading-7 text-slate-600">
                <div><dt className="font-semibold text-slate-900">输入代码后为什么还不能加入？</dt><dd>先确认输入的是六位A股股票代码，并保留开头的0。等待识别完成再操作。若显示「打开已有记录」，直接打开原档案。若只有部分数据缺失，以页面标注为准。</dd></div>
                <div><dt className="font-semibold text-slate-900">情绪周期的「板块启动」怎么看？</dt><dd>系统同时检查板块涨幅、匹配到的涨停股数量和最早首次涨停时间。具体阈值在情绪周期的「设置与说明」中查看。三项都满足才标为启动。真实行情中，时间取该行业在涨停池中匹配到的股票的最早首次涨停时间。没有匹配或缺少时间时会显示「未知」。</dd></div>
                <div><dt className="font-semibold text-slate-900">为什么看到几个不同的日期？</dt><dd>公开行情有供应商时间和本机获取时间，休市时通常显示最近报价。日K线有自己的截至交易日，红利列表有扫描快照日期。查看公司详情时以各指标旁的来源、日期与口径为准。缺失值或延迟未知要保留为未知。</dd></div>
                <div><dt className="font-semibold text-slate-900">回撤预警怎么算？</dt><dd>驾驶舱与市场雷达共用当前资产、资产峰值和回撤上限。预警点是上限的50%、75%、90%和100%。上限20%时对应10%、15%、18%和20%。出入金会改变资产口径，更新资产与峰值时要一起核对。价格跳空等情况可能直接越过预警线。</dd></div>
                <div><dt className="font-semibold text-slate-900">公司笔记保存在哪里？</dt><dd>驾驶舱、公司档案和决策复盘保存在当前浏览器。同一股票代码只用一份公司档案，移出观察池后仍可在个股研究找到笔记。清理网站数据或换浏览器可能看不到原记录。情绪周期人工确认独立保存，综合研究档案和模拟账户保存在本地后端。</dd></div>
                <div><dt className="font-semibold text-slate-900">系统能同步券商或下单吗？</dt><dd>当前支持手动维护和本地券商快照导入。公开行情会更新，真实账户的资金、持仓和成交仍以券商为准。模拟交易使用虚拟账户，实际成交约束只在相应工具支持时纳入。</dd></div>
                <div><dt className="font-semibold text-slate-900">模拟数据、真实行情和AI怎么看？</dt><dd>情绪周期的真实入口展示已采集行情和快照，真实历史回测仍受数据覆盖限制。CSV结果依赖导入数据，演示数据用于熟悉界面。估值和组合推演随假设变化，AI输出属于待核实分析。历史统计不代表未来，结果仅供研究。</dd></div>
              </dl>
            </section>}
            {activePage === "basics" && <section id="basics" className="scroll-mt-6">
              <h4 className="text-xl font-semibold">常用术语</h4>
              <dl className="mt-4 divide-y divide-slate-100">
                {basics.map(([term, definition]) => <div className="py-3" key={term}><dt className="font-semibold">{term}</dt><dd className="mt-1 text-sm leading-7 text-slate-600">{definition}</dd></div>)}
              </dl>
              <div className="flex flex-wrap gap-4 border-t border-slate-100 pt-4 text-sm text-emerald-800 underline underline-offset-4">
                <a href="https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml" target="_blank" rel="noreferrer">上交所交易规则</a>
                <a href="https://www.sse.com.cn/assortment/fund/etf/question/" target="_blank" rel="noreferrer">上交所ETF问答</a>
                <a href="https://investor.szse.cn/warning/activities/fundIntroduction/t20210122_584364.html" target="_blank" rel="noreferrer">深交所基金风险说明</a>
              </div>
            </section>}

            {activePage === "knowledge" && <section>
              <h3 className="text-xl font-semibold">知识 · 课程目录</h3>
              <p className="mt-2 text-sm leading-7 text-slate-700">从市场基础学到回测验证。每课都有独立的概念讲解、算例、自测和速查分页。</p>
              <p className="mt-2 text-xs leading-6 text-slate-500">进度保存在当前浏览器，重启项目后可继续。</p>
              <ol className="mt-4 divide-y divide-slate-200">
                {courses.map(({ id, title }, index) => (
                  <li key={id}>
                    <a className="block py-3 text-sm font-semibold text-emerald-900 hover:underline" href={courseUrl(id)}>
                      <span className="mr-2 text-xs font-normal text-slate-500">第 {index + 1} 课</span>{title}
                      {progress.completed.includes(id) && <span className="ml-2 inline-block rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-900">已完成</span>}
                    </a>
                  </li>
                ))}
              </ol>
            </section>}

            {activePage === "after-roadmap" && <section id="after-roadmap" className="scroll-mt-6">
              <h4 className="text-xl font-semibold">D150 之后</h4>
              <p className="mt-3 text-sm leading-7 text-slate-700">从基本面中长线、规则化波段、量化选股与组合中选一条，用接下来90天检验。分别关注企业与估值的变化、规则能否一致执行、组合在成本和样本外检验后的表现。路线图的验收仍以模拟样本、风险上限和明确退出规则为依据。</p>
            </section>}
          </>}
          <a className="inline-block rounded-md px-2 py-2 text-sm font-medium text-emerald-800 underline underline-offset-4 md:hidden" href="#guide-contents">返回目录</a>
        </div>
      </div>
    </article>
  );
}

function CourseContent({ index, part, completed, onToggleCompletion }: { index: number; part: string; completed: boolean; onToggleCompletion: () => void }) {
  const course = courses[index];
  const previous = courses[index - 1];
  const next = courses[index + 1];
  const [first, last] = course.range;
  const topics = knowledgeChapters.flatMap(({ lessons }) => lessons).filter(([day]) => day >= first && day <= last);

  return (
    <>
      <section>
        <a className="text-sm font-medium text-emerald-800 underline underline-offset-4" href={pageUrl("knowledge")}>返回课程目录</a>
        <h3 className="mt-3 text-2xl font-semibold text-slate-950">{course.title}</h3>
        <nav aria-label="本课分页" className="mt-4 flex flex-wrap gap-2">
          {courseParts.map(({ id, title }) => <a key={id} className={`${secondaryButtonClass} aria-[current=page]:border-emerald-400 aria-[current=page]:bg-emerald-50`} aria-current={part === id ? "page" : undefined} href={courseUrl(course.id, id)}>{title}</a>)}
        </nav>
        {part === "concepts" && <div className="mt-3 divide-y divide-slate-100">
          {course.sections.map(([title, text]) => (
            <section className="py-4" key={title}>
              <h4 className="font-semibold text-slate-950">{title}</h4>
              <p className="mt-2 text-sm leading-7 text-slate-700">{text}</p>
            </section>
          ))}
        </div>}
        {part === "example" && <section className="mt-5 border-t border-slate-200 pt-4">
          <h4 className="font-semibold text-emerald-900">跟着算例走一遍</h4>
          <p className="mt-2 text-sm leading-7 text-slate-700">{course.example}</p>
        </section>}
      </section>
      {part === "quiz" && <section>
        <h4 className="text-lg font-semibold">课后自测</h4>
        <p className="mt-2 text-sm leading-7 text-slate-700">{course.question}</p>
        <details className="mt-3 text-sm">
          <summary className="cursor-pointer font-semibold text-emerald-900">查看答案与解析</summary>
          <p className="mt-2 leading-7 text-slate-700">{course.answer}</p>
        </details>
      </section>}
      {part === "reference" && <section>
          <h4 className="text-lg font-semibold">本课知识点速查</h4>
          <ol start={first} className="mt-3 divide-y divide-slate-100">
            {topics.map(([day, title, explanation]) => {
              const code = `D${String(day).padStart(3, "0")}`;
              return (
                <li id={code} key={day} className="py-3">
                  <h5 className="text-sm font-semibold"><span className="mr-2 font-mono text-emerald-800">{code}</span>{title}</h5>
                  <p className="mt-1 text-sm leading-7 text-slate-700">{explanation}</p>
                </li>
              );
            })}
          </ol>
      </section>}
      <nav aria-label="课程顺序" className="flex flex-wrap justify-between gap-2">
        {previous && <a className={secondaryButtonClass} href={courseUrl(previous.id)}>上一课 · {previous.title}</a>}
        <button type="button" className={secondaryButtonClass} onClick={onToggleCompletion}>{completed ? "撤销完成标记" : "标记本课完成"}</button>
        {next && <a className={`${secondaryButtonClass} ml-auto`} href={courseUrl(next.id)}>下一课 · {next.title}</a>}
      </nav>
    </>
  );
}
