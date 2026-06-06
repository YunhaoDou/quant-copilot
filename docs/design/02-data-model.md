# 系统设计 · 数据模型

> v0.1 · 2026-06-06 · 表设计草案

## 总览

| 表 | 用途 | 主要索引 |
|---|---|---|
| `users` | 邮箱 + 哈希密码 | uniq(email) |
| `tickers` | ticker 元数据 | uniq(symbol, market) |
| `prices` | OHLCV 时序数据 | PK(ticker_id, date) + BRIN(date) |
| `research_notes` | LLM 生成的结构化研究笔记 | (user_id, ticker_id, created_at desc) |
| `strategies` | 策略模板 + 默认参数 | uniq(name) |
| `backtest_runs` | 回测元数据 + 总体指标 | (user_id, created_at desc) |
| `backtest_curves` | 回测权益曲线时序 | PK(run_id, date) |
| `paper_accounts` | 多纸面账户 | (user_id) |
| `paper_positions` | 当前持仓 | uniq(account_id, ticker_id) |
| `paper_orders` | 委托 + 成交记录 | (account_id, placed_at desc) |
| `llm_calls` | LLM 调用日志 + 缓存追踪 | (cache_key) + (created_at) |

## 详细 schema(草案,Phase 1 落地时可能微调)

### users
```sql
CREATE TABLE users (
  id BIGSERIAL PRIMARY KEY,
  email VARCHAR(255) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  last_login_at TIMESTAMPTZ
);
```

### tickers
```sql
CREATE TABLE tickers (
  id BIGSERIAL PRIMARY KEY,
  symbol VARCHAR(20) NOT NULL,
  market VARCHAR(10) NOT NULL,  -- US, CN, HK 等
  name VARCHAR(255),
  industry VARCHAR(100),
  last_sync_at TIMESTAMPTZ,
  UNIQUE(symbol, market)
);
CREATE INDEX idx_tickers_market ON tickers(market);
```

### prices(时序大表)
```sql
CREATE TABLE prices (
  ticker_id BIGINT NOT NULL REFERENCES tickers(id),
  date DATE NOT NULL,
  open DOUBLE PRECISION,
  high DOUBLE PRECISION,
  low DOUBLE PRECISION,
  close DOUBLE PRECISION,
  volume BIGINT,
  adj_close DOUBLE PRECISION,
  PRIMARY KEY (ticker_id, date)
);
-- BRIN 是为时序数据优化的轻量索引,适合 prices 这种按日期顺序追加的表
CREATE INDEX idx_prices_date_brin ON prices USING BRIN(date);
```

### research_notes
```sql
CREATE TABLE research_notes (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id),
  ticker_id BIGINT NOT NULL REFERENCES tickers(id),
  content JSONB NOT NULL,  -- 结构化:thesis, bullish_points, catalysts, risks 等
  llm_model VARCHAR(50),
  llm_call_id BIGINT REFERENCES llm_calls(id),
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_notes_user_ticker ON research_notes(user_id, ticker_id, created_at DESC);
-- JSONB 字段可以创建 GIN 索引做全文搜索(Phase 2 后期)
```

### backtest_runs / backtest_curves(主从)
```sql
CREATE TABLE backtest_runs (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id),
  strategy_id BIGINT NOT NULL REFERENCES strategies(id),
  params JSONB NOT NULL,
  metrics JSONB,  -- sharpe, max_drawdown, total_return 等
  start_date DATE,
  end_date DATE,
  status VARCHAR(20),  -- pending / running / done / failed
  error TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);

CREATE TABLE backtest_curves (
  run_id BIGINT NOT NULL REFERENCES backtest_runs(id) ON DELETE CASCADE,
  date DATE NOT NULL,
  equity DOUBLE PRECISION,
  drawdown DOUBLE PRECISION,
  PRIMARY KEY (run_id, date)
);
```

### llm_calls(成本追踪 + 缓存)
```sql
CREATE TABLE llm_calls (
  id BIGSERIAL PRIMARY KEY,
  cache_key VARCHAR(255) NOT NULL,  -- 由 (ticker, prompt_version, day) 组合 hash
  model VARCHAR(50),
  input_tokens INTEGER,
  output_tokens INTEGER,
  cost_usd NUMERIC(10, 4),
  cached BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_llm_cache_key ON llm_calls(cache_key);
CREATE INDEX idx_llm_created_at ON llm_calls(created_at);
```

## 迁移策略

- 用 **Alembic** 管理 schema 演进
- 不允许直接 `ALTER TABLE` 生产库,必须走 migration
- 命名:`YYYYMMDD_HHMM_brief_description.py`

## 备份(Phase 4+)

- Railway Postgres 自带每日备份
- 重要表(`research_notes` / `backtest_runs`)每周导出 JSON 到对象存储
