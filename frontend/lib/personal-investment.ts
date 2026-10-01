export type AllocationKey = "stable" | "index" | "stocks" | "cash";

export type InvestorProfile = {
  initialCapital: number;
  monthlyContribution: number;
  peakAssets: number;
  currentAssets: number;
  maxDrawdownPct: number;
  allocations: Record<AllocationKey, number>;
};

export type Holding = {
  id: string;
  code: string;
  name: string;
  marketValue: number;
  cost: number;
  thesis: string;
};

export type WatchItem = {
  id: string;
  code: string;
  name: string;
  price: number;
  pe: number;
  dividendYield: number;
  qualityScore: number;
  targetLow: number;
  targetHigh: number;
  riskTags: string;
  status: "观察" | "接近区间" | "已进入区间" | "排除";
};

export type ResearchNote = {
  id: string;
  code: string;
  name: string;
  businessModel: string;
  financialTrend: string;
  valuationThesis: string;
  catalysts: string;
  bearCase: string;
  invalidation: string;
  updatedAt: string;
};

export type DecisionEntry = {
  id: string;
  date: string;
  code: string;
  action: "观察" | "买入" | "加仓" | "减仓" | "卖出" | "复盘";
  amount: number;
  reason: string;
  evidence: string;
  risks: string;
  exitCondition: string;
  lesson: string;
};

export type MarketEnvironment = {
  trend: number;
  policy: number;
  liquidity: number;
  sentiment: number;
  updatedAt: string;
  notes: string;
};

export type MarketTheme = {
  id: string;
  name: string;
  policy: number;
  prosperity: number;
  capital: number;
  leadership: number;
  catalyst: number;
  thesis: string;
  risks: string;
};

export type PersonalInvestmentState = {
  profile: InvestorProfile;
  holdings: Holding[];
  watchlist: WatchItem[];
  research: ResearchNote[];
  journal: DecisionEntry[];
  marketEnvironment: MarketEnvironment;
  marketThemes: MarketTheme[];
};

export const STORAGE_KEY = "quant-copilot-personal-investment-v1";

export const DEFAULT_STATE: PersonalInvestmentState = {
  profile: {
    initialCapital: 100_000,
    monthlyContribution: 5_000,
    peakAssets: 100_000,
    currentAssets: 100_000,
    maxDrawdownPct: 20,
    allocations: { stable: 50, index: 25, stocks: 15, cash: 10 },
  },
  holdings: [],
  watchlist: [],
  research: [],
  journal: [],
  marketEnvironment: {
    trend: 3,
    policy: 3,
    liquidity: 3,
    sentiment: 3,
    updatedAt: "",
    notes: "",
  },
  marketThemes: [],
};

export function getMarketEnvironment(environment: MarketEnvironment) {
  const score = Math.round(
    ((environment.trend * 0.3 + environment.policy * 0.25 + environment.liquidity * 0.25 + environment.sentiment * 0.2) - 1) * 25,
  );
  if (score >= 70) return { score, label: "偏强", range: [65, 80] as const, tone: "text-emerald-700", action: "顺势参与主线，但保留现金并避免情绪高潮追高。" };
  if (score >= 55) return { score, label: "均衡", range: [45, 65] as const, tone: "text-sky-700", action: "保持均衡仓位，只在证据充分的方向分批试仓。" };
  if (score >= 40) return { score, label: "谨慎", range: [25, 45] as const, tone: "text-amber-700", action: "降低出手频率，等待趋势、资金和情绪形成共振。" };
  return { score, label: "防守", range: [0, 25] as const, tone: "text-red-700", action: "以现金和稳健资产为主，不逆势扩大个股风险。" };
}

export function getThemeScore(theme: MarketTheme) {
  return Math.round(((theme.policy * 0.2 + theme.prosperity * 0.25 + theme.capital * 0.2 + theme.leadership * 0.2 + theme.catalyst * 0.15) - 1) * 25);
}

export function getRiskAdjustedEquityCap(drawdownPct: number) {
  if (drawdownPct >= 18) return 25;
  if (drawdownPct >= 15) return 40;
  if (drawdownPct >= 10) return 50;
  return 80;
}

export type RiskStage = {
  level: "正常" | "观察" | "收缩" | "防守" | "触线";
  color: string;
  background: string;
  instruction: string;
};

export function getDrawdownPct(peakAssets: number, currentAssets: number): number {
  if (peakAssets <= 0 || currentAssets >= peakAssets) return 0;
  return ((peakAssets - currentAssets) / peakAssets) * 100;
}

export function getRiskStage(drawdownPct: number): RiskStage {
  if (drawdownPct >= 20) {
    return {
      level: "触线",
      color: "text-red-800",
      background: "bg-red-100 border-red-300",
      instruction: "停止新增个股风险，复核全部持仓与资产配置，优先恢复风险预算。",
    };
  }
  if (drawdownPct >= 18) {
    return {
      level: "防守",
      color: "text-red-700",
      background: "bg-red-50 border-red-200",
      instruction: "股票总仓位降至约25%，只保留逻辑最强且流动性充足的仓位。",
    };
  }
  if (drawdownPct >= 15) {
    return {
      level: "收缩",
      color: "text-orange-700",
      background: "bg-orange-50 border-orange-200",
      instruction: "削减最弱逻辑和高相关仓位，暂停非计划加仓。",
    };
  }
  if (drawdownPct >= 10) {
    return {
      level: "观察",
      color: "text-amber-700",
      background: "bg-amber-50 border-amber-200",
      instruction: "暂停新增个股，检查亏损来源、行业集中度和逻辑失效条件。",
    };
  }
  return {
    level: "正常",
    color: "text-emerald-700",
    background: "bg-emerald-50 border-emerald-200",
    instruction: "按计划分批投入，单只个股首次仓位不超过3%。",
  };
}

export function getRiskBudget(profile: InvestorProfile) {
  const drawdownPct = getDrawdownPct(profile.peakAssets, profile.currentAssets);
  const maxLoss = profile.peakAssets * (profile.maxDrawdownPct / 100);
  const currentLoss = Math.max(0, profile.peakAssets - profile.currentAssets);
  return {
    drawdownPct,
    maxLoss,
    currentLoss,
    remaining: Math.max(0, maxLoss - currentLoss),
    stage: getRiskStage(drawdownPct),
  };
}

export function positionShock(
  totalAssets: number,
  positionPct: number,
  stockLossPct: number,
) {
  const positionValue = totalAssets * (positionPct / 100);
  const lossAmount = positionValue * (stockLossPct / 100);
  return {
    positionValue,
    lossAmount,
    portfolioLossPct: totalAssets > 0 ? (lossAmount / totalAssets) * 100 : 0,
    remainingAssets: Math.max(0, totalAssets - lossAmount),
  };
}

export type ValuationInputs = {
  currentEps: number;
  years: number;
  growthPct: number;
  pe: number;
  dividendYieldPct: number;
};

export function valuationScenarios(input: ValuationInputs) {
  const scenario = (growthPct: number, pe: number, dividendYieldPct: number) => {
    const futureEps = input.currentEps * Math.pow(1 + growthPct / 100, input.years);
    const terminalPrice = Math.max(0, futureEps * pe);
    const dividends = Math.max(
      0,
      input.currentEps * pe * (dividendYieldPct / 100) * input.years,
    );
    return {
      growthPct,
      pe,
      dividendYieldPct,
      futureEps,
      terminalPrice,
      dividends,
      totalValue: terminalPrice + dividends,
    };
  };

  return {
    bear: scenario(input.growthPct - 8, Math.max(3, input.pe - 4), Math.max(0, input.dividendYieldPct - 1)),
    base: scenario(input.growthPct, input.pe, input.dividendYieldPct),
    bull: scenario(input.growthPct + 6, input.pe + 4, input.dividendYieldPct + 1),
  };
}

export function makeId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}
