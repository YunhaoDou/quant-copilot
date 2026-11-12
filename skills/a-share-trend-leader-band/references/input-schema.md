# 输入契约

`scripts/evaluate.py --input <json>` 只接受本文件定义的字段。所有字段由调用方（Agent 或数据层）
从行情/账户系统取数后填入，**脚本不取数、不补数据**。路径写法 `a.b.c` 表示 JSON 嵌套层级。

## 两种取数模式

脚本按 `account.has_position` 切换链路，必需字段不同：

| 模式 | 判定链路 | 必需字段 |
|---|---|---|
| 建仓模式（`false`） | 环1 → 环2 → 环3 → 环5 | `as_of`、`data_timestamp`、`market.*`、`account.has_position`、`sector.amount_share_history`、`sector.limit_up_counts`、`sector.has_tier_no_gap`、`sector.adjustment_resilient`、`stock.symbol`、`stock.price`、`stock.is_mainline_mid_cap`、`stock.market_cap_yi`、`stock.ma.*`、`stock.above_ma10_long`、`stock.volume_pattern_ok`、`stock.institutional_resonance` |
| 持仓模式（`true`） | 只跑环4 | `as_of`、`data_timestamp`、`market.*`、`account.has_position`、`stock.symbol`，外加 `stock.exit.close_below_ma20`；`sector` 可选（给了就参与退潮判定）、`stock.price` 可选（只影响止损价输出） |

`mainline.require_tier_no_gap` / `require_adjustment_resilient` / `leader.require_*` 为 `false` 时，
对应的 `sector.*` / `stock.*` 布尔字段可省略。

## 单位与类型约定

写错类型/单位会被脚本 REJECT（`stage=数据校验`、`reason=DATA_TYPE_INVALID`），不要靠猜：

- `amount_share_history`：占比**小数**，8% 写 `0.08`，不是 `8`。
- 市值、成交额：单位**亿元**，300 亿写 `300`。
- `volume_shrink_ratio`：相对均量的比例，取值 `(0,1]`，缩量到一半写 `0.5`（不要写 `50`）。
- `pullback_to_ma`：整数周期（`5` / `10` / `20`），`10.9` 会被拒绝。
- 所有时间戳：带时区偏移的 ISO 8601，如 `2026-11-11T15:00:00+08:00`；**不带时区会被拒绝**。
- 所有数值必须是有限数；`NaN` / `Infinity` 会被拒绝。

`data_timestamp` 不得晚于 `as_of`，任何未来时间戳均 REJECT。

## 顶层

| 字段 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `as_of` | string | 是 | 判定时点，用真实当前时间；脚本用它算数据新鲜度 |
| `data_timestamp` | string | 是 | 行情数据本身的截止时间，不是取数时间 |
| `market` | object | 是 | 见下 |
| `sector` | object | 建仓模式必需 / 持仓可选 | 见下 |
| `stock` | object | 是 | 见下 |
| `account` | object | 是 | 见下 |

## `market`

| 字段 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `env` | string | 是 | `bull` / `range` / `bear`，必须是 `position.env_caps` 的键；未知值 REJECT |
| `index_above_key_ma` | bool | 是 | 大盘指数是否在关键均线（如 20/60 日线）上方。`env=bull` 而此值为 `false` 属于字段冲突，判定降级/仓位上限归零 |

## `sector` —— 环1 主线数据（持仓模式下可选，仅用于退潮信号）

| 字段 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `name` | string | 否 | 板块名称，仅用于输出 |
| `amount_share_history` | number[] | 建仓模式是 | 最近 3—5 个交易日的板块成交额占比（小数），按时间升序 |
| `limit_up_counts` | int[] | 建仓模式是 | 最近 2—5 个交易日的板块涨停家数，按时间升序 |
| `has_3board_plus` | bool | 否 | 塔尖是否有 3 板及以上高标（仅记录，不参与判定） |
| `has_tier_no_gap` | bool | 建仓模式是 | 梯队是否无断层（塔尖/二板/首板齐全） |
| `adjustment_resilient` | bool | 建仓模式是 | 最近一个调整日是否抗跌有承接 |
| `breakdown` | bool | 否 | 板块梯队是否已瓦解（默认 false）。持仓模式下也生效（减仓信号） |
| `laggards_collapsed` | bool | 否 | 后排跟风是否批量大跌/炸板掉队（默认 false）。同上 |

## `stock`

| 字段 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `symbol` | string | 是 | 代码 |
| `price` | number | 建仓模式是 / 持仓可选 | 判定时点价格，用于算止损价；持仓模式缺失时 `stop_loss_price` 为 `null` |
| `is_mainline_mid_cap` | bool | 建仓模式是 | 是否为第一主线内的趋势中军（而非情绪先锋）。口径见 framework.md 环2 |
| `market_cap_yi` | number | 建仓模式是 | 总市值（亿元） |
| `avg_turnover_yi` | number | 否 | 近期日均成交额（亿元） |
| `turnover_history_yi` | number[] | 否 | 最近 3 个交易日成交额（亿元）；`avg_turnover_yi` 缺失时用连续 ≥20 亿判定 |
| `ma` | object | 建仓模式是 | 键为 `config.leader.ma_periods` 里的周期字符串（默认 `"5"`、`"10"`、`"21"`、`"55"`），值为数值 |
| `above_ma10_long` | bool | 建仓模式是 | 是否长期运行在 10 日线上方 |
| `volume_pattern_ok` | bool | 建仓模式是 | 上涨放量/回调缩量是否成立 |
| `institutional_resonance` | bool | 建仓模式是 | 机构/北向/游资是否共振（龙虎榜长期净买入） |
| `entry` | object | 未持仓时是 | 环3，见下 |
| `exit` | object | 持仓时是 | 环4，见下。缺失或 `close_below_ma20` 为 `null` 时环4 返回 `WAIT`（`EXIT_NO_DATA`）且仓位上限归零；`close_below_ma20` 类型错则为 `REJECT`（`DATA_TYPE_INVALID`）。两种情况都**不会**给安慰性的 `HOLD` |

### `stock.entry` —— 环3 买点数据

| 字段 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `pullback_to_ma` | int/数字字符串 | 是 | 回踩的均线周期，必须是 `entry.allowed_ma` 之一（默认 5/10/20） |
| `intraday_break_recovered` | bool | 是* | 盘中破线是否尾盘收回 |
| `volume_shrink_ratio` | number | 是 | 回踩期间成交量 / 均量，取值 `(0,1]`；> `entry.volume_shrink_ratio_max` 视为缩量不足 |
| `stabilizing_candle` | bool | 是* | 是否出现小阳/十字星/带下影线止跌形态 |
| `next_day_confirm` | bool | 是* | 次日是否翻红或放量阳线反包 |
| `far_from_ma10` | bool | 是* | 股价是否已显著远离 10 日线，`true` 直接 REJECT |

\* 对应 `entry.require_*` 配置为 `false` 时可省略。

**缺失行为**：`stock.entry` 或任一必需字段缺失 → 环3 返回 `WAIT`（`ENTRY_NO_DATA`），**不会当成通过**。
字段类型/取值错误 → REJECT（`DATA_TYPE_INVALID`），例如 `far_from_ma10: "true"`、`volume_shrink_ratio: 40`。

### `stock.exit` —— 环4 卖点数据

| 字段 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `close_below_ma20` | bool | 持仓模式是 | **收盘**是否有效跌破 20 日线（MA 定义由调用方负责）。盘中击穿不要置 true。缺失/`null` → `WAIT`（`EXIT_NO_DATA`）；非布尔类型 → `REJECT`（`DATA_TYPE_INVALID`） |
| `high_volume_stall` | bool | 否 | 是否高位放量滞涨（默认 false）→ 减仓信号 |
| `intraday_below_ma20` | bool | 否 | 盘中是否跌破。`exit.require_close_confirm=true` 时只提示不触发；`false` 时直接触发卖点 |

`config.exit.ma_exit` 当前仅支持20，其他值配置校验失败。

## 模式与被忽略的数据块

脚本只校验**当前模式实际消费**的数据块：

- 建仓模式：校验 `sector` / `stock.entry` / 均线与量价，**不校验** `stock.exit`（坏掉的 exit 不会挡住建仓判定）。
- 持仓模式：校验 `stock.exit` 与可选 `sector.breakdown` / `laggards_collapsed`，**不校验** `stock.entry` / `stock.ma`。

展示型字段（`stock.symbol`、`sector.name`）若不是字符串，输出里会被净化为 `null`，保证 stdout 是严格 JSON（不含 `NaN`）。

## `account`

| 字段 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `has_position` | bool | 是 | 是否已持有该标的。`true` 只跑环4；`false` 建仓链路 |
| `total_asset` | number | 否 | 总资产，仅透传，不参与判定 |

## 最小合法输入（建仓模式）

```json
{
  "as_of": "2026-11-11T15:30:00+08:00",
  "data_timestamp": "2026-11-11T15:00:00+08:00",
  "market": { "env": "bull", "index_above_key_ma": true },
  "sector": {
    "amount_share_history": [0.04, 0.06, 0.09],
    "limit_up_counts": [6, 7],
    "has_tier_no_gap": true,
    "adjustment_resilient": true
  },
  "stock": {
    "symbol": "000000",
    "price": 11.8,
    "is_mainline_mid_cap": true,
    "market_cap_yi": 300,
    "avg_turnover_yi": 20,
    "ma": { "5": 12.0, "10": 11.5, "21": 11.0, "55": 10.0 },
    "above_ma10_long": true,
    "volume_pattern_ok": true,
    "institutional_resonance": true,
    "entry": {
      "pullback_to_ma": 10,
      "intraday_break_recovered": true,
      "volume_shrink_ratio": 0.4,
      "stabilizing_candle": true,
      "next_day_confirm": true,
      "far_from_ma10": false
    }
  },
  "account": { "has_position": false }
}
```

## 最小合法输入（持仓模式）

每日核对卖点只需要这些——不用重新取一遍主线/龙头数据：

```json
{
  "as_of": "2026-11-11T15:30:00+08:00",
  "data_timestamp": "2026-11-11T15:00:00+08:00",
  "market": { "env": "range", "index_above_key_ma": true },
  "stock": {
    "symbol": "600000",
    "price": 11.2,
    "exit": { "close_below_ma20": false, "high_volume_stall": false }
  },
  "account": { "has_position": true }
}
```

## 错误契约（退出码 2）

输入/配置文件读不了、配置结构不合法或内部异常时，stdout 输出最小错误契约，**不是**完整判定输出：

```json
{
  "stage": "配置校验",
  "decision": "REJECT",
  "reasons": [{ "code": "CONFIG_INVALID", "msg": "..." }],
  "human_confirm_required": true,
  "next_action": "修正问题后重跑；未产出判定结果前不得交易"
}
```

`stage` 可能为 `配置加载` / `配置校验` / `内部错误`。argparse 用法错误（如漏 `--input`）直接退出 2，不输出 JSON。

### 新增字段

- `stock.ma_slopes`：与均线相同周期的当日均线减前一交易日均线，需全为正。
- `account.invested_pct`：已用总仓位比例（0至1）。
- `account.cash_pct`：可用现金占总资产比例（0至1），与已用仓位合计不得超过1。
- `account.stop_loss_price`：持仓固定止损价，建仓时保存，不随现价下调。
