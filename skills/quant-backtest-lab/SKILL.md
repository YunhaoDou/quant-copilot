---
name: quant-backtest-lab
license: MIT
github: https://github.com/YunhaoDou/quant-copilot
description: >
  Backtest 4 parameterized strategy templates (SMA crossover, RSI mean reversion,
  time-series momentum, Bollinger reversion) against real US or CN equity history,
  vectorbt-driven. No database, no API key. Triggered when the user wants to backtest
  a trading strategy, compare strategy templates on a ticker, or run a parameter sweep
  (e.g. "帮我回测 AAPL 的 SMA 策略", "backtest 600519", "sweep fast/slow on this ticker").
metadata:
  author: YunhaoDou
  version: "0.1.0"
---

# quant-backtest-lab

单文件、零配置的策略回测工具，从 [quant-copilot](https://github.com/YunhaoDou/quant-copilot) 的回测引擎抽取而来。不需要数据库、不需要 API key，跑一个命令就能拿到收益/夏普/回撤/胜率。

## 前置检查

```bash
pip install -r "${CLAUDE_SKILL_DIR}/requirements.txt"
```

## 用法

**四策略对比**（不传 `--strategy` 默认跑全部 4 个模板）：

```bash
python "${CLAUDE_SKILL_DIR}/scripts/backtest.py" --market us --ticker AAPL --start 2014-01-01 --end 2025-12-31
```

**A 股同样支持**（交易所前缀自动识别：6/9 开头 → sh，0/3 开头 → sz）：

```bash
python "${CLAUDE_SKILL_DIR}/scripts/backtest.py" --market cn --ticker 600519 --start 2014-01-01 --end 2025-12-31
```

**单策略**：

```bash
python "${CLAUDE_SKILL_DIR}/scripts/backtest.py" --market us --ticker AAPL --strategy sma_crossover
```

**参数扫描**（笛卡尔积，验证参数变化确实改变输出，而非硬编码结果）：

```bash
python "${CLAUDE_SKILL_DIR}/scripts/backtest.py" --market us --ticker AAPL --strategy sma_crossover \
  --sweep fast=5,10,20 slow=30,60
```

**对比买入持有**（`--vs-buyhold`，验证"技术指标择时"类说法是否站得住）：

```bash
python "${CLAUDE_SKILL_DIR}/scripts/backtest.py" --market us --ticker AAPL --vs-buyhold
```

## 4 个策略模板

| key | 说明 | 默认参数 |
|---|---|---|
| `sma_crossover` | 快慢均线金叉/死叉 | fast=10, slow=30 |
| `rsi_reversion` | RSI 超卖买入/超买卖出 | window=14, low=30, high=70 |
| `momentum` | 时序动量突破 | lookback=20, threshold=0.0 |
| `bollinger_reversion` | 布林带下轨买入/中轨卖出 | window=20, num_std=2.0 |

## 输出字段

`return`（总收益率）· `sharpe`（夏普比率）· `maxDD`（最大回撤）· `winRate`（胜率）· `trades`（交易笔数）

引擎用 `vectorbt.Portfolio.from_signals`，初始资金 10 万、手续费 0.1%，日频。回测结果基于真实历史行情计算，不是模拟数据。

## 局限

- 无滑点建模，无 T+1 限制（A 股实盘需自行调整）
- 单标的，不支持组合回测
- akshare 接口偶尔限流，报错重试即可
