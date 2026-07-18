---
name: ticker-research-lab
license: MIT
github: https://github.com/YunhaoDou/quant-copilot
description: >
  Generate a grounded equity research note (thesis / catalysts / risks / fair value range)
  for a US ticker. Real fundamentals (P/E, margins, revenue growth, ROE) and real recent news
  headlines are fetched via yfinance and injected into the LLM prompt — the model must cite
  which fetched fact backs each catalyst/risk, it cannot invent numbers. Triggered when the
  user wants a stock research note, fundamental summary, or thesis on a ticker (e.g. "帮我研究一下
  AAPL", "research this stock", "TSLA 的投资逻辑是什么").
metadata:
  author: YunhaoDou
  version: "0.1.0"
---

# ticker-research-lab

零数据库、单文件的个股研究笔记生成器，从 [quant-copilot](https://github.com/YunhaoDou/quant-copilot) 的 LLM 研究模块重写而来——原版直接把 ticker 扔给模型让它凭训练记忆编 thesis，这版先真实抓基本面和新闻，逼模型只能基于抓到的事实说话。

## 前置检查

```bash
pip install -r "${CLAUDE_SKILL_DIR}/requirements.txt"
```

需要一个 OpenAI 兼容的 chat completions 端点（默认 DeepSeek）：

```bash
export LLM_API_KEY=sk-xxxxx        # 必需
export LLM_BASE_URL=https://api.deepseek.com   # 可选，默认 DeepSeek
export LLM_MODEL=deepseek-chat                 # 可选
```

## 用法

```bash
python "${CLAUDE_SKILL_DIR}/scripts/research.py" --ticker AAPL
```

## 输出内容

- **依据（基本面）**：sector / marketCap / 现价 / 静态PE / 动态PE / 净利率 / 营收增速 / ROE / 总营收 / 分析师评级，全部来自 yfinance 实时数据
- **依据（新闻）**：最近 5 条真实新闻标题（`--news-limit` 可调）
- **Thesis / Catalysts / Risks**：LLM 生成，每条 catalyst/risk 要求标注依据哪条事实/新闻
- **Fair value range**：模型估值区间
- 结尾固定输出免责声明

## 防幻觉设计

- system prompt 明确要求"只能基于给定事实，不能编造数字或事件"
- 抓到的原始事实块和 LLM 输出一起打印，读者可以逐条核对模型有没有编
- schema 校验失败会把错误信息喂回模型重试（最多 2 次），而不是静默接受坏输出

## 局限

- 只支持美股（yfinance 覆盖范围）
- 新闻只取标题，不做全文抓取和情感分析
- 免责声明不能替代真实尽调，仅作研究辅助
