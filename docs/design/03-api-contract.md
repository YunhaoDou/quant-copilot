# 系统设计 · API 草案

> v0.1 · 2026-06-06 · 仅列出主要 endpoint,完整版以 `/docs`(OpenAPI)为准

## 风格

- REST,JSON
- 路径用 kebab-case,资源复数
- 错误:`{detail: string, code?: string}` + HTTP 状态码
- 认证:Bearer JWT
- 分页:`?limit=20&cursor=xxx`,游标式
- 时间:ISO 8601 UTC

## 公开端点

| Method | Path | 用途 |
|---|---|---|
| GET | `/` | 服务信息 |
| GET | `/health` | 健康检查(DB + Redis)|
| GET | `/docs` | OpenAPI Swagger |

## Auth(Phase 1)

| Method | Path | 用途 |
|---|---|---|
| POST | `/auth/register` | 邮箱注册 |
| POST | `/auth/login` | 返回 JWT |
| POST | `/auth/logout` | 失效 token(blacklist)|
| GET | `/auth/me` | 当前用户 |

## Tickers / Prices(Phase 1)

| Method | Path | 用途 |
|---|---|---|
| GET | `/tickers?q=...&market=US` | 搜索 |
| GET | `/tickers/{symbol}` | 单 ticker 元数据 |
| GET | `/tickers/{symbol}/prices?from=&to=&interval=1d` | OHLCV |
| POST | `/tickers/{symbol}/sync` | 触发数据同步任务 |

## Research(Phase 2)

| Method | Path | 用途 |
|---|---|---|
| POST | `/research/start` | 开始一个 LLM 研究任务,返回 job_id |
| GET | `/research/jobs/{job_id}` | 任务状态 + 结果 |
| GET | `/research/notes?user_id=...&ticker=NKE` | 历史研究笔记 |
| DELETE | `/research/notes/{id}` | 删除 |

### POST /research/start 请求示例
```json
{
  "ticker": "NKE",
  "market": "US",
  "depth": "standard"
}
```

### 结果 schema(LLM 结构化输出)
```json
{
  "thesis": "...",
  "bullish_points": ["...", "..."],
  "bearish_points": ["...", "..."],
  "catalysts": [{"event": "...", "date": "2026-08-15"}],
  "risks": [...],
  "fair_value_range": {"low": 95, "high": 145, "currency": "USD"},
  "confidence": 0.7
}
```

## Backtest(Phase 3)

| Method | Path | 用途 |
|---|---|---|
| GET | `/strategies` | 策略模板列表 |
| POST | `/backtests` | 提交回测任务 |
| GET | `/backtests/{run_id}` | 任务详情 + 指标 |
| GET | `/backtests/{run_id}/curve` | 权益曲线时序 |
| POST | `/backtests/compare` | 多策略对比 |

## Paper Trading(Phase 4)

| Method | Path | 用途 |
|---|---|---|
| GET | `/paper/accounts` | 我的账户列表 |
| POST | `/paper/accounts` | 创建新账户 |
| POST | `/paper/orders` | 下单 |
| GET | `/paper/positions?account_id=...` | 持仓 |
| GET | `/paper/pnl?account_id=...&from=&to=` | P&L 时序 |
| POST | `/paper/position-size` | 仓位计算器(无副作用)|

## Risk(Phase 4)

| Method | Path | 用途 |
|---|---|---|
| GET | `/risk/{account_id}` | 风险面板数据 |

## 速率限制

| 端点类 | 限制 |
|---|---|
| `/auth/*` | 10 req/min/IP |
| `/research/start` | 20 req/day/user(LLM 调用贵) |
| 其他 | 100 req/min/user |

实现:Redis + 滑动窗口算法
