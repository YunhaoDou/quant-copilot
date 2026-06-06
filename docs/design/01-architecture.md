# 系统设计 · 架构

> v0.1 · 2026-06-06

## 高层架构

```
┌─────────────────────────────────────────┐
│  Next.js 前端 (Vercel)                  │
│  Dashboard / Research / Backtest /      │
│  Paper Trading / Risk                   │
└──────────────────┬──────────────────────┘
                   │ REST + WebSocket(Phase 4)
┌──────────────────▼──────────────────────┐
│  FastAPI 后端 (Railway)                 │
│  routes / services / models / db        │
└──────┬──────────┬───────────────┬───────┘
       │          │               │
┌──────▼──┐  ┌────▼─────┐   ┌─────▼──────┐
│Postgres│  │  Redis   │   │ Celery     │
│时序+元数据│  │缓存+队列  │   │ Workers    │
└─────────┘  └──────────┘   └─────┬──────┘
                                  │
              ┌───────────────────┼─────────────────┐
              │                   │                 │
      ┌───────▼─────┐    ┌────────▼──────┐   ┌──────▼──────┐
      │ Backtest    │    │ LLM Call      │   │ Data Sync   │
      │ Worker      │    │ Worker        │   │ Cron Worker │
      └─────────────┘    └────────┬──────┘   └─────────────┘
                                  │
                          ┌───────▼────────┐
                          │ Claude/OpenAI  │
                          └────────────────┘
```

## 关键模块(后端 app/ 下)

| 模块 | 职责 |
|------|------|
| `routes/` | HTTP 路由,薄薄一层 — 校验输入、调 service、返回响应 |
| `services/` | 业务逻辑 — 数据获取、LLM 编排、回测调度、风控计算 |
| `models/` | SQLAlchemy ORM 模型(关系表) |
| `db/` | 引擎和 session 管理,迁移用 Alembic |
| `tasks/` | Celery 任务定义 |
| `config.py` | Pydantic settings 集中环境变量 |

## 数据流(典型例子:用户查 NKE 研究)

```
1. 前端 POST /research/start { ticker: "NKE" }
2. 后端 services.research.kick_off():
   - 写入 research_jobs(状态 pending)
   - 触发 Celery 任务 research_ticker.delay("NKE", job_id)
   - 立即返回 {job_id} 给前端
3. 前端轮询 GET /research/status/{job_id} 或订阅 WebSocket
4. Worker 并行执行:
   - 拉公司基本面(akshare / yfinance)
   - 拉最新财报 + 新闻
   - 调 Claude API + Structured Output
   - 写入 research_notes(完成)
5. 前端拿到结果,展示
```

## 部署

| 环境 | 后端 | 前端 | DB | Redis |
|------|------|------|------|------|
| 本地开发 | docker-compose | docker-compose | docker-compose | docker-compose |
| 生产 | Railway(单实例)| Vercel | Railway Postgres | Railway Redis |

## 性能预算

- API p50 < 200ms(读),< 500ms(写)
- 回测任务 < 30s(5 年数据 1 个策略)
- LLM 研究任务 < 60s
- 前端首屏 LCP < 2.5s

## 弹性策略

- DB / Redis 连接失败:返回 503 + retry-after
- LLM 限流:指数退避,最多 3 次
- 数据源失败:fallback 到本地缓存(即使过期也可读)
