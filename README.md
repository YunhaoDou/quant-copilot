# Quant Copilot

> LLM-powered quant research platform. Personal-use MVP — research a ticker with AI, backtest your ideas, paper-trade them, review the data.

![Backend](https://github.com/YunhaoDou/quant-copilot/actions/workflows/backend.yml/badge.svg)
![Frontend](https://github.com/YunhaoDou/quant-copilot/actions/workflows/frontend.yml/badge.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)

**Status**: Phase 0 — scaffold complete. Project ramp-up.

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

## 本地启动

需要安装 Docker。

```bash
git clone https://github.com/YunhaoDou/quant-copilot
cd quant-copilot
cp .env.example .env
docker-compose up
```

启动后:

- 后端 API: http://localhost:8000
- 后端 API 文档: http://localhost:8000/docs
- 前端: http://localhost:3000
- Postgres: localhost:5432(用户 `quant`)
- Redis: localhost:6379

验证健康:

```bash
curl http://localhost:8000/health
# {"status":"ok","components":{"database":{...},"redis":{...}}}
```

## 开发

### Backend 单独跑

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# 启动 Postgres + Redis 容器:
docker-compose up postgres redis
# 开后端 dev server:
uvicorn app.main:app --reload
# 测试:
pytest
# Lint:
ruff check .
```

### Frontend 单独跑

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

## Roadmap

- ✅ Phase 0 · Scaffold + docker-compose + 设计文档
- ⏳ Phase 1 · 数据基础(W1-W2)
- ⏳ Phase 2 · LLM 研究助手(W3-W4)
- ⏳ Phase 3 · 回测引擎(W5-W6)
- ⏳ Phase 4 · 纸面交易 + 风险面板(W7)
- ⏳ Phase 5 · 上线 + 演示视频(W8)

完整项目章程见 Obsidian `AI量化研究平台.md`。

## License

[MIT](LICENSE)
