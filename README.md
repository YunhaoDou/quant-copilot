# Quant Copilot

> LLM-powered quant research platform. Personal-use MVP — research a ticker with AI, backtest your ideas, paper-trade them, review the data.

![Backend](https://github.com/YunhaoDou/quant-copilot/actions/workflows/backend.yml/badge.svg)
![Frontend](https://github.com/YunhaoDou/quant-copilot/actions/workflows/frontend.yml/badge.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)

**Status**: M1 (data), M3 (backtest engine), and a slice of M2 (LLM research) are implemented and
verified against real data. Paper trading (M4), the risk panel (M5), and deployment (M6) are not
built yet — out of scope for this pass. See "What's real vs. open" below.

## 想法

Bloomberg 太贵,雪球太浅,ChatGPT 套壳没意义。在中间做一个**单人量化研究平台**:

- **Research**:输入 ticker → LLM 自动拉财报/新闻/公司简介 → 输出结构化 thesis + catalysts + risks + 公允价值
- **Backtest**:选策略模板 → 跑 5 年回测 → 出权益曲线 + 指标
- **Paper trade**:多账户、市价/限价/止损单、实时 P&L、风险面板
- **Anti-noise**:所有"稳赚战法"在这里都要拿数据说话

## 技术栈

| 层 | 选型 |
|---|---|
| 前端 | Next.js 14 + TypeScript + Tailwind + TanStack Query |
| 后端 | FastAPI + Pydantic v2 + SQLAlchemy 2.0(async) |
| 数据库 | Postgres 16(BRIN 索引时序表)|
| 缓存 / 队列 | Redis 7 |
| 后台任务 | Celery |
| 回测 | vectorbt |
| LLM | Claude API(主),OpenAI(备),Structured Output |
| 部署 | 后端 Railway,前端 Vercel |

完整架构见 [docs/design/01-architecture.md](docs/design/01-architecture.md)。

## 仓库结构

```
quant-copilot/
├── backend/         FastAPI + Celery + SQLAlchemy
├── frontend/        Next.js 14 App Router
├── shared/          跨端共享类型(后期由 OpenAPI 生成)
├── docs/design/     系统设计文档 + ADRs
├── docker-compose.yml
└── .github/workflows/
```

## 本地启动(不需要 Docker)

这台开发机没装 Docker,以下用 Homebrew 装的原生 Postgres 16 + Redis 跑通、验证过。`docker-compose.yml`
保留且与当前 schema/配置一致,装了 Docker 之后 `docker-compose up` 应该同样能跑,但本仓库尚未在 Docker
里实测过。

```bash
brew install postgresql@16 redis
brew services start postgresql@16
brew services start redis
createuser -s quant
psql -d postgres -c "CREATE DATABASE quantcopilot OWNER quant;"
psql -d postgres -c "ALTER USER quant WITH PASSWORD 'devpassword';"
```

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

export DATABASE_URL="postgresql+asyncpg://quant:devpassword@localhost:5432/quantcopilot"
export REDIS_URL="redis://localhost:6379/0"
export CELERY_BROKER_URL="redis://localhost:6379/1"
export CELERY_RESULT_BACKEND="redis://localhost:6379/2"
# 真实的 LLM 研究助手需要一把真 key,没有也不影响数据/回测部分:
export ANTHROPIC_API_KEY="sk-ant-..."

uvicorn app.main:app --reload          # http://localhost:8000 ,建表 + 种子策略在启动时自动跑
celery -A app.tasks.celery_app worker --loglevel=info   # 另开一个终端,跑异步回测/研究任务
pytest                                  # 测试用独立的 quantcopilot_test 库
ruff check app tests
```

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev   # http://localhost:3000
```

页面:`/ticker`(拉数据 + K 线)、`/backtest`(4 策略对比 + 权益曲线)、`/research`(LLM 研究笔记)。

## 什么是真的,什么还没做

**已实现并用真实数据验证过**(不是 mock):

- **M1 数据基础**:`akshare`(Sina 接口 `stock_zh_a_daily`;Eastmoney 的 `stock_zh_a_hist` 在这台机器
  网络环境下连接不稳定,已切换)拉取真实 A 股日线,upsert 进 Postgres(`ticker_symbol + trade_date`
  唯一索引,`trade_date` 上有 BRIN 索引)。已用贵州茅台(600519)真实拉取 2014-01-02 至今约 3000+ 根
  日线验证。
- **M3 回测引擎**:4 个策略模板(SMA 交叉、RSI 均值回归、时序动量、布林带回归),基于 vectorbt,对同一
  只股票 11 年真实历史跑出的收益/夏普/回撤/胜率**互不相同**(不是硬编码);参数扫描接口验证过 `fast/slow`
  改变确实改变结果;4 策略横向对比接口验证过,回测结果和权益曲线持久化进 `backtest_runs` /
  `backtest_curves`。
- **M2 一个切片:LLM 研究助手**:Pydantic schema 校验 + 校验失败自动重试(最多 2 次,把失败原因喂回给
  模型重新生成)+ Redis 按 ticker 缓存(默认 24h)。这台机器上**没有**可用的 `ANTHROPIC_API_KEY`,所以
  真实 LLM 调用没跑通;编排逻辑(重试/缓存/schema 校验)用一个假 client 在 `tests/test_llm_research.py`
  里做了单元测试(5 个用例:首次成功、schema 违规后重试成功、JSON 解析失败后重试成功、重试耗尽后抛错、
  第二次调用命中缓存不再调 LLM)。
- **Celery 后台任务**:`/backtest/compare` 和 `/research` 都支持 `run_async: true`,真实起了一个
  worker 验证过——发起请求立即拿到 `task_id`,worker 异步跑完后通过 `/backtest/task/{id}` 能拿到结果。

**还没做,明确排除在这一轮之外**:

- M4 纸面交易、M5 风险面板 —— 没建表也没做接口
- M6 部署上线(Railway/Vercel)—— 没有部署,只在本地验证过
- Docker 内验证 —— 这台机器没装 Docker Desktop,只验证了原生 Postgres/Redis 跑法;`docker-compose.yml`
  保持与当前代码一致但没实测过 `docker-compose up`
- LLM 研究助手的真实端到端调用 —— 需要一把真的 `ANTHROPIC_API_KEY`
- Alembic 迁移 —— 目前用 `Base.metadata.create_all()` 在启动时建表,够 MVP 用,后续要迁移历史再补
  Alembic

## Roadmap

- ✅ Phase 0 · Scaffold + docker-compose + 设计文档
- ✅ M1 · 数据基础(真实 akshare 拉取 + Postgres 存储)
- ✅ M3 · 回测引擎(4 策略 + 参数扫描 + 对比,vectorbt)
- ✅ M2(切片)· LLM 研究助手(schema 校验 + 重试 + 缓存,逻辑已测试,真实调用待真 key)
- ⏳ M4 · 纸面交易
- ⏳ M5 · 风险面板
- ⏳ M6 · 部署上线 + 演示视频

完整项目章程见 Obsidian `AI量化研究平台.md`(注意:本仓库这一轮只对齐简历要点,不是把 M1-M6 全做完)。

## License

[MIT](LICENSE)
