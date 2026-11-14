# Quant Copilot

> A 股个人投资决策系统：环境 / 主线 / 情绪 → 研究 → 策略前向模拟 → 复盘。
> 仓库里同时保留早期「美股研究 MVP」栈作为独立 API 子系统，两套面共享一个后端进程。

![Backend](https://github.com/YunhaoDou/quant-copilot/actions/workflows/backend.yml/badge.svg)
![Frontend](https://github.com/YunhaoDou/quant-copilot/actions/workflows/frontend.yml/badge.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)

## 现在是什么

| 产品面 | 入口 | 数据 / 存储 | 状态 |
|---|---|---|---|
| **A 股个人投资系统（主线）** | 前端 `/invest`，6 个工作流页面 / 18 个子页签 | 腾讯行情、东方财富、akshare、SHIBOR；SQLite 账本 | 持续迭代中 |
| **遗留美股研究栈（M1–M5）** | 仅 API（无独立页面） | yfinance + Postgres + vectorbt | 保留可用，不再扩展 |

前端只有 `/invest` 一个真实路由（`/` 会跳转过去）。旧版 README 里的 `/ticker`、`/backtest`、`/research`、`/paper`
页面已不存在——对应能力收进 `/invest` 的工作流页面。设计文档 `docs/design/` 是归档的 v0.1 草案，
**不是当前实现的说明书**，详见 [docs/design/README.md](docs/design/README.md)。

### 页面地图（6 个工作流页面，功能一个不少）

| 页面 | 子页签（括注为旧视图名） |
|---|---|
| 决策台 | 驾驶舱（dashboard） / 决策复盘（journal） |
| 市场 | 市场雷达（market，含环境·主线·股债趋势） / 情绪周期（cycle） |
| 研究 | 红利扫描（dividends） / 观察池（watchlist） / 个股研究（research） |
| 交易与模拟 | 策略研究（strategies） / 模拟工具（tools） / 历史回测 / 手动模拟 / 分析档案 |
| 数据与工具 | 股票与ETF行情 / 多因子选股 / 基金与ETF |
| 指南与设置 | 新手指南（guide） / 系统设置 / 旧合规问答 |

URL 规范：`/invest?view=<页面>&tab=<子页签>`，页面内面板继续用 `&section=`（如 `view=research&tab=research&section=ai-note`）。
旧链接（`view=functions&tool=backtest`、`view=strategies&strategy=...`、`view=dashboard` 等）仍可用，加载时会自动规范化到新地址。

## 主要功能（A 股）

- **A股驾驶舱**：资产、持仓、回撤防线、个人风险预算，浏览器本地档案例。
- **市场雷达**：`/market/radar` 环境/主线候选/政策证据；股债趋势（沪深300ETF × 国债ETF 真实趋势）。
- **情绪周期**：真实涨停池/板块梯队/连板高度，人工确认阶段；「启动—分歧—回补」影子账户。
- **红利看板**：全 A 股分红扫描 + 六维财务证据 + 价格位置 + 基准对比。
- **观察池 / 个股研究**：统一公司档案、研究区间；技术诊断与追问、AI 结构化笔记。
- **策略研究（8 类）**：质量价值、红利现金流、红利低波、基本面改善后趋势、相对强势趋势、情绪龙头回补、
  主线趋势中军波段、SHIBOR 红利成长轮动。每类独立前向模拟账户，保守撮合（整手、涨跌停、滑点、费用、T+1）。
- **模拟工具 / 决策复盘**：仓位与估值、组合概率推演；证据-退出-教训的复盘时间线。
- **数据与工具**：股票与 ETF 行情、多因子选股、基金与 ETF；历史回测、手动模拟、分析档案在
  「交易与模拟」内；系统设置与旧合规问答在「指南与设置」内。
- **新手指南**：产品课程、金融知识、项目说明与阅读材料。

## 技术栈

| 层 | 选型 |
|---|---|
| 前端 | Next.js 14 + TypeScript + Tailwind + TanStack Query |
| 后端 | FastAPI + Pydantic v2 + SQLAlchemy 2.0 (async) |
| 存储 | Postgres 16（遗留栈模型）；SQLite（cycle 前向账本、研究档案、全A/交易所母表缓存） |
| 缓存 / 队列 | Redis 7 + Celery（beat：财报任务） |
| 回测 | vectorbt（4 个美股模板）；cycle 内另有事件驱动策略引擎 |
| 行情 | 腾讯 `qt.gtimg.cn`（实时报价 + 前复权日线）、东方财富数据中心（全A/涨停池/基金/板块）、akshare、SHIBOR、yfinance（遗留美股）、SEC EDGAR（财报流水线） |
| LLM | DeepSeek（默认，OpenAI 兼容）；页面可切换 OpenAI / Anthropic / Gemini，支持代理 |
| 桌面桥接 | `integrations/vnpy_quant_copilot`（vn.py 4.x，八策略页签，只读本机服务） |
| Skills | `skills/` 下 3 个独立 Skill；后端 `cycle/trend_leader.py` 运行时加载其中五环规则 |

## 快速开始

```bash
# 一键（Postgres/Redis 已在 brew 装好）
./start.sh            # 后端 8000 + 前端 3000 + Celery；./start.sh backend|frontend 可分开
./stop.sh             # 停止
```

手动启动（等价）：

```bash
brew install postgresql@16 redis && brew services start postgresql@16 && brew services start redis
createuser -s quant
psql -d postgres -c "CREATE DATABASE quantcopilot OWNER quant;"
psql -d postgres -c "ALTER USER quant WITH PASSWORD 'devpassword';"

cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export DATABASE_URL="postgresql+asyncpg://quant:devpassword@localhost:5432/quantcopilot"
export REDIS_URL="redis://localhost:6379/0"
export CELERY_BROKER_URL="redis://localhost:6379/1"
export CELERY_RESULT_BACKEND="redis://localhost:6379/2"
uvicorn app.main:app --reload            # http://localhost:8000（启动时建表 + 种子策略；接口见 /docs）
celery -A app.tasks.celery_app worker --loglevel=info    # 另开终端
celery -A app.tasks.celery_app beat --loglevel=info      # 另开终端（财报定时任务）

cd ../frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev    # http://localhost:3000 → /invest
```

行情与账本数据落地在 `backend/data/`（`cycle/{events,live,dividends}.sqlite`、`research-lab.sqlite`、
交易所母表等），已被 `.gitignore` 排除。

## LLM 与通知配置

- **唯一入口**：`功能中心 → 系统设置 → 模型与通知`（`GET/PUT /research-lab/config`），可配置供应商、模型、
  API key、代理、Lark/Discord webhook。
- **环境变量兜底**：`backend/.env` 的 `DEEPSEEK_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`；
  页面配置优先于环境变量。
- `连接与缓存` 只保留后端地址、新闻缓存 TTL 与维护动作；模型 key 不再在两处重复维护。

## vn.py 桌面桥接

```bash
python integrations/install_vnpy_bridge.py --vnpy <你的 vn.py 源码目录>   # 追加安装，可回滚
```

桥接只连 `http://127.0.0.1:8000` 的模拟接口，展示八策略账户/持仓/成交/日志；**不做下单路由**。
详见 [integrations/vnpy_quant_copilot/README.md](integrations/vnpy_quant_copilot/README.md)。

## Skills

| Skill | 用途 |
|---|---|
| `skills/a-share-trend-leader-band` | 五环闸门确定性判定（主线→龙头→买点→卖点→仓位），stdlib-only，117 条测试 |
| `skills/quant-backtest-lab` | 独立回测 CLI（vectorbt，4 模板，美股/ A股） |
| `skills/ticker-research-lab` | 独立美股研究笔记 CLI（yfinance 基本面与新闻 + DeepSeek） |

用户级安装（可选）：`ln -s "$PWD/skills/a-share-trend-leader-band" ~/.agents/skills/`。
注意：`backend/app/cycle/trend_leader.py` 会在运行时按相对路径加载 `skills/a-share-trend-leader-band/scripts/evaluate.py`，
部署时 `skills/` 必须与 `backend/` 同级。

## 验证

```bash
cd backend && .venv/bin/python -m pytest -q          # 需要本地 Postgres 的 quantcopilot_test 库
.venv/bin/python -m ruff check app tests
cd frontend && npx tsc --noEmit && npm run build
cd skills/a-share-trend-leader-band && python3 -m pytest tests -q
```

已知环境相关失败：`tests/test_fund_analysis.py::test_get_premium_snapshot_real_etf` 依赖外网行情，离线环境会失败。

## 已知边界（当前取舍，不是 bug）

- **没有认证**：早期 JWT 配置与 `python-jose`/`passlib` 依赖已移除，当前 API 未实现认证；后端只应在本机/内网使用。
- **没有 Alembic**：启动时 `Base.metadata.create_all()` 建表（`backend/alembic/` 为空）。
- **两套模拟口径**：手动模拟交易（无费用/T+1/涨跌停）与 cycle 前向模拟（有）并存，口径差异记录在
  [docs/2026-11-06-live-validation.md](docs/2026-11-06-live-validation.md)。
- **历史回测覆盖有限**：8 个 A 股策略只有「相对强势趋势」是纯价量规则、可做历史回测；其余 7 类依赖历史财务/分红/事件/成分/利率快照（系统只保存最新值），只做前向模拟，避免前视偏差。见「交易与模拟 → 历史回测」页内的可用性说明。
- **遗留美股栈**只保留 API 与脚本，没有专属页面；其模拟协议见 [docs/sim-protocol.md](docs/sim-protocol.md)。
  4 个旧模板与标普500基准的系统模拟账户保留原名 `sim-*`，界面显示中文名；可在「交易与模拟 → 策略研究」只读查看净值与收益，账户/订单仍在「交易与模拟 → 手动模拟」。
- 全部输出只用于研究与风险管理，**不构成投资建议**，不产生实盘交易指令。

## 仓库结构

```
quant-copilot/
├── backend/app/
│   ├── routes/       遗留美股研究栈 API（tickers/backtest/research/paper/...）
│   ├── services/     遗留栈服务 + LLM/研究/基金/风控 + indicators 等共享计算
│   ├── cycle/        A 股行情、情绪周期、红利、全A扫描、八个策略前向账本（SQLite）
│   ├── models/       Postgres 模型（遗留栈）
│   └── tasks/        Celery worker / beat
├── frontend/         Next.js：/invest 单页 + 6 个工作流页面（components/invest）
├── integrations/     vn.py 桌面桥接（只读本机模拟服务）
├── skills/           独立 Agent Skill（五环闸门、回测、个股研究）
├── docs/             sim-protocol（在用）、design/（归档 v0.1）、历史验收记录
├── docker-compose.yml
├── start.sh / stop.sh
└── .github/workflows/
```

## 文档索引

- [docs/sim-protocol.md](docs/sim-protocol.md) —— 遗留美股日频模拟协议（仍在用）
- [docs/design/README.md](docs/design/README.md) —— 归档的 v0.1 设计草案（勿据此接入）
- [docs/2026-11-06-terminal-migration.md](docs/2026-11-06-terminal-migration.md) / [live-validation](docs/2026-11-06-live-validation.md) / [market-radar](docs/2026-11-07-market-radar.md) —— 历史验收与迁移记录（日期快照）
- 现行接口：启动后端后访问 `http://localhost:8000/docs`（OpenAPI 是 API 的唯一事实源）

## License

[MIT](LICENSE)

## 性能与只读验收

系统设置的“运行与性能”可查看缓存、行情资源和数据源授权状态。
在项目目录执行 `backend/.venv/bin/python backend/scripts/verify_system.py` 可运行统一验收；不调用AI、不操作真实交易。外部IOPV用例需显式选择，未授权源保持关闭。

实现、复跑方式及实测限制见 [最终优化记录](docs/performance-final.md) 和 [性能待办](docs/performance-todo.md)。
