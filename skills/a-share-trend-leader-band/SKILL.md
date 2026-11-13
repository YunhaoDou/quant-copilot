---
name: a-share-trend-leader-band
license: MIT
github: https://github.com/YunhaoDou/quant-copilot
description: >
  Deterministic five-gate execution skill for A-share "trend + leader swing"
  trading — 主线定方向 → 龙头定标的 → 买点定时机 → 卖点定生死 → 仓位定存活.
  The gate logic lives in a stdlib-only script: any failed, missing, stale or
  self-contradictory gate returns REJECT/WAIT, and the agent may never skip a
  gate, relax a threshold, fabricate data, or emit an order without human
  confirmation. Triggered when the user wants to screen / monitor / review
  A-share candidates with this framework, or asks to turn the process into an
  agent skill (e.g. "帮我按主线龙头筛A股", "这个板块算不算主线", "这个位置能不能买",
  "是不是该止损了", "把趋势龙头波段做成 skill").
metadata:
  author: YunhaoDou
  version: "0.1.0"
---

# a-share-trend-leader-band

A股「趋势+龙头波段」五环闸门的**规则执行器**。Agent 负责取数、填输入、调用脚本、展示结果并请求人工确认；
脚本负责逐环判定。任一环不通过即停止——不自动下单、不主观补数据、不跳环。

> 免责声明：本 Skill 仅用于规则执行与研究复盘，不构成投资建议，不产生实盘交易指令。

## 何时使用

- 用户要求按主线、龙头、买点、卖点、仓位五环筛选或监控 A 股候选。
- 用户要求判断某板块是否为主线、某股是否为趋势中军、是否出现买点/卖点。
- 用户要求把这套流程交给炒股 Agent 执行，或要求把流程做成 Skill。

## 前置检查

只依赖 Python 3.10+ 标准库，无需安装任何第三方包：

```bash
python3 --version
```

## 核心原则

1. 必须按顺序执行：环1 主线 → 环2 龙头 → 环3 买点 → 环4 卖点 → 环5 仓位。任一环不通过，立即停止后续环节。
2. 数据缺失、过期、字段冲突一律视为「不通过」。禁止猜测、补全、放宽阈值。
3. 禁止因「涨得猛」「再不买来不及」「这次不一样」跳环。
4. Agent 只输出候选、信号、理由、风险、建议仓位上限和人工确认请求；未经人工确认不得生成实盘下单指令。
5. 已持仓时**只跑环4**（环1/环2 是建仓门槛，持仓后不重复判定；板块退潮通过 `sector.breakdown` / `sector.laggards_collapsed` 进入环4）。未持仓才走环1→环2→环3→环5。
6. 不得建议亏损补仓；不得在有效跌破 20 日线后建议「等反弹」；不得在板块退潮期提高仓位。
7. 所有阈值来自 `config.json`，Agent 无权自行修改。阈值变更必须回测 + 人工审批。

## 目录

```
a-share-trend-leader-band/
├── SKILL.md
├── config.json              # 所有阈值（唯一真相源）
├── scripts/evaluate.py      # 确定性五环判定，stdout 输出 JSON
├── references/
│   ├── framework.md         # 五环判定口径与依据
│   ├── input-schema.md      # 输入字段契约（含单位陷阱）
│   └── forbidden.md         # 禁止清单，违反即执行失败
├── examples/
│   ├── input.json           # 通过五环 → BUY_CANDIDATE
│   ├── input_reject_mainline.json  # 一日游题材 → REJECT（环1）
│   └── input_hold_exit.json # 持仓跌破20日线 → EXIT（环4）
└── tests/test_evaluate.py   # 边界回归测试
```

## 两种取数模式

脚本按 `account.has_position` 自动切换，两种模式的必需字段不同（详见 `references/input-schema.md`）：

| 模式 | 判定链路 | 必需数据 |
|---|---|---|
| 建仓模式（`has_position: false`） | 环1 → 环2 → 环3 → 环5 | 板块成交额占比/涨停家数/梯队、个股均线与量价、买点信号 |
| 持仓模式（`has_position: true`） | 只跑环4 | 大盘环境 + `stock.symbol` + `stock.exit.close_below_ma20`；`sector` 可选（给了就参与退潮判定）、`stock.price` 可选（只影响止损价输出） |

持仓模式故意不要求板块/龙头数据：每日核对卖点不该因为「重新取一遍主线数据」而卡住。
两种模式都只校验**当前模式实际消费的数据块**：建仓模式忽略 `stock.exit`，持仓模式忽略 `stock.entry`。

## 用法

1. 按 `references/input-schema.md` 从行情/账户系统取数，生成输入 JSON（必须带 `as_of` 与 `data_timestamp`）。
2. 运行脚本，**以脚本输出为准**：

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/evaluate.py" \
  --input /tmp/candidate.json \
  --config "${CLAUDE_SKILL_DIR}/config.json"
```

`--config` 省略时默认用脚本上一级目录的 `config.json`。

退出码：

- `0` = 已产出判定（`REJECT` / `WAIT` 也是有效结果）。
- `2` = 输入/配置读不了或结构不合法。stdout 输出**最小错误契约**（不是完整判定输出）：
  `stage`（`配置加载` / `配置校验` / `内部错误`）、`decision: REJECT`、`reasons`、`human_confirm_required`、`next_action`。
  argparse 用法错误（如漏 `--input`）直接退出 2，不输出 JSON。

可以先跑自带示例验证环境：

```bash
cd "${CLAUDE_SKILL_DIR}"
python3 scripts/evaluate.py --input examples/input.json                # BUY_CANDIDATE
python3 scripts/evaluate.py --input examples/input_reject_mainline.json # REJECT（环1）
python3 scripts/evaluate.py --input examples/input_hold_exit.json       # EXIT（环4）
```

## 输出契约

脚本输出 JSON，字段固定齐全（判定失败的分支也一样，Agent 不用写特例；退出码 2 的错误契约除外）：

| 字段 | 含义 |
|---|---|
| `stage` | 当前环节（数据校验 / 环1…环5；持仓模式下环1/环2 不参与） |
| `decision` | `BUY_CANDIDATE` / `WAIT` / `REJECT` / `EXIT` / `REDUCE` / `HOLD` |
| `mainline_status` / `leader_status` / `entry_signal` / `exit_signal` | 各环状态；持仓模式下环1/环2/环3 为 `NOT_APPLICABLE` |
| `position_cap_pct` | 建议仓位**上限**（占总资金 %，环境单票上限与单笔风控取小），不是目标仓位；`REDUCE`/`HOLD` 时它是环境单票上限，**不是加仓许可** |
| `stop_loss_price` / `risk_amount_pct` | 止损价与止损时占总资金比例 |
| `data_freshness` / `data_age_hours` / `missing_fields` | 数据可用性 |
| `reasons` | `[{code, msg}]`，拒绝/等待/减仓原因 |
| `human_confirm_required` | 恒为 `true` |
| `next_action` / `audit_log_id` | 下一步动作与审计号 |

决策与允许动作：

| decision | Agent 允许做什么 |
|---|---|
| `BUY_CANDIDATE` | 展示候选、理由、止损价、仓位上限，请求人工确认。**不得下单** |
| `WAIT` | 说明还缺哪个确认信号，继续监控 |
| `REJECT` | 不交易，说明被哪一环挡下 |
| `EXIT` | 请求人工确认离场，不得改口「等反弹」 |
| `REDUCE` | 请求人工确认减仓/收缩 |
| `HOLD` | 持有并列出每日需核对的卖点 |

## 五环速查

| 环 | 核对项 | 不通过时 |
|---|---|---|
| ① 主线 | 成交额占比 ≥8% 且连续放大；涨停连续 2 日 ≥5 家；梯队无断层；调整日抗跌 | `REJECT`；占比 ≥5% 但条件不全为 `WATCH`/`WAIT` |
| ② 龙头 | 主线趋势中军、非情绪先锋；市值 150—1000 亿**且**（日均成交额 10—30 亿，或连续 3 日 ≥20 亿）；5>10>21>55 多头排列；机构/北向/游资共振 | `REJECT` |
| ③ 买点 | 缩量回踩 5/10/20 日线不破；量能 ≤均量一半；止跌 K 线 + 次日翻红确认；不追远离 10 日线 | `WAIT`（追高为 `REJECT`；缺买点字段一律 `WAIT`） |
| ④ 卖点 | 收盘有效跌破 20 日线（无条件离场）；高位放量滞涨（减仓）；板块梯队瓦解（减仓） | `EXIT` / `REDUCE` |
| ⑤ 仓位 | 环境总仓上限与单笔风控（止损亏损 ≤ 总资金 2%）取小；`bull` 与指数位置矛盾时降级 | 给上限并请求确认 |

完整口径与依据见 `references/framework.md`；输入字段与单位陷阱见 `references/input-schema.md`。

## 数据校验与 fail-closed

判定只认数据，不认「大概齐」。失败方向必须朝「不通过」：

| 情况 | 结果 |
|---|---|
| 缺必需字段、数据过期/未来、未知 `market.env`、数值类型或单位错（占比写成 8、NaN/Infinity） | `REJECT`（`stage=数据校验`） |
| 买点字段缺失 | `WAIT`（`ENTRY_NO_DATA`），不是放行 |
| 买点字段类型/取值错（`far_from_ma10` 写成字符串、缩量比 40 或 -0.2、回踩周期 10.9） | `REJECT`（`DATA_TYPE_INVALID`） |
| 持仓中 `stock.exit` 缺失 / `close_below_ma20` 为 `null` | `WAIT`（`EXIT_NO_DATA`），仓位上限归零，绝不返回安慰性 `HOLD` |
| 持仓中 `close_below_ma20` 类型错（如字符串 `"true"`） | `REJECT`（`DATA_TYPE_INVALID`） |
| 时间戳缺时区 | `REJECT`（无法比较新鲜度） |
| `data_timestamp` 晚于 `as_of` | 拒绝，禁止未来数据 |
| 配置阈值类型/范围/顺序不合法（如 `single > total`、`ma_periods` 非递增、连续窗口 <2、`risk_per_trade` 越界） | 退出码 `2` + `CONFIG_INVALID`，不跑判定 |

## 阈值配置约束

`config.json` 不只是数字容器，脚本会先校验再判定，不合法直接退出码 2：

- 环境仓位：`0 < single <= total <= 1`，`single` 是单票上限、`total` 是总仓上限。
- 单笔风控：`risk_per_trade ∈ (0,1]`，`stop_loss_pct ∈ (0,1)`；两者之比反推单票风控上限。
- 连续窗口：`mainline.consecutive_expand_days`、`consecutive_limit_up_days`、
  `leader.consecutive_turnover_20e8_days` 必须 ≥2（窗口为 1 等于取消「连续」条件）。
- 均线周期：`leader.ma_periods` 必须是递增正整数（如 `[5,10,21,55]`），顺序反了会把多头排列判反。
- `mainline.potential_share <= mainline.strong_share`，`entry.allowed_ma` 非空正整数数组。

改阈值 = 改策略假设，必须回测 + 人工审批；Agent 不得为了「通过」而调参。

## 执行纪律

- 脚本返回 `REJECT` / `WAIT` 时，**不得**输出买入建议，也不得自行重写规则后给出相反结论。
- 不得修改 `config.json`。用户要改阈值时，先说明这是新策略假设，需要回测 + 人工审批。
- 不得把「符合规则但亏损」直接归因于规则失效；先看统计样本和单笔风控是否被执行。
- 违反 `references/forbidden.md` 任一条 = Skill 执行失败。

## 局限

- 只做规则判定，不取数、不预测、不择时优化；数据质量由调用方保证。
- 板块梯队、调整日抗跌、资金共振等定性项由调用方按 `input-schema.md` 口径落成布尔字段，本 Skill 不替你判断盘感。
- 环5 的「趋势清晰度定集中度」维度未实现：只按市场环境与单笔风控给上限，清晰度需人工判断。
- `exit.ma_exit` 当前只允许20；`close_below_ma20` 由调用方按自己定义的 20 日线判定收盘是否有效跌破。
- 持仓模式不重跑环1/环2，板块退潮只认 `sector.breakdown` / `sector.laggards_collapsed` 两个显式信号。
- 回测与参数调优不在本 Skill 范围内。

## 真实数据接入（2026-11-12）

策略中心的「趋势中军波段 · 真实数据核验」输入证券代码后调用 `GET /trend-leader/{symbol}`。
复用项目腾讯公开报价与不复权日线，展示供应商报价时间、日线截止日期和缺失证据。
没有 Mock 回退；接口失败返回错误，不产生通过信号。输入、配置及输出以审计号保存到本地SQLite。
本适配层尚无可核验的多日板块占比、资金共振、回踩确认及真实账户预算，因此仅提供数据核验，不能自动模拟建仓。

新增边界：
- 板块 `breakdown` 或 `laggards_collapsed` 为真时禁止建仓。
- 建仓须提供 `account.invested_pct` 与 `cash_pct`（0至1，合计不得大于1）；仓位受剩余环境预算与现金限制。
- 建仓须提供 `stock.ma_slopes`，各配置周期斜率均需为正。
- 持仓 `account.stop_loss_price` 是建仓时保存的固定防线，触及时输出退出；不再从持仓现价下移止损。
  未提供时输出止损价为null，均线退出仍可核验，不能据此声称固定止损已执行。
- T+1、停牌、涨跌停和成交容量由模拟撮合层负责；该skill不直接成交。

## 第七策略：独立前向模拟

页面：`/invest?view=trade&tab=strategies&strategy=trend-leader-band`。
与相对强势趋势最接近，区别是先核验主线和中军，再等待缩量回踩与次日确认；
与情绪龙头回补不同，不按固定第3/4/5天交易，不抢连板，也不沿用旧策略的固定15%止盈。

- `GET /trend-forward`：独立账户、采集日期、跟踪范围、判断和成交记录。
- `POST /trend-forward/start|pause|exit`：继续、暂停、请求模拟退出。
- 页面查询代码会加入跟踪，后台另从当时完整涨停池补充观察标的，按轮转批次核验。
- 从启用后保存完整板块与涨停池快照；之前只有18板块/12龙头的截取历史不冒充完整证据。
- 独立10万元虚拟账户持久化到SQLite。按后续新鲜报价、T+1、涨跌停、费用和滑点撮合；不回填旧价格。
- 固定止损以实际模拟成交价保存。固定止损和已完成日线的20日线退出单独核验。
- 严格版本的主线占比、趋势中军地位、资金共振及完整买点证据尚未全部接通；缺任一必需证据不会建仓。
  快照采集与账户运行不代表已经产生有效信号，也不代表等待若干天一定会成交。
- `REDUCE`首版以全部退出单仓实现，属于明确披露的保守模拟近似；尚未支持分批减仓。
- 不复权价格遇除权不连续存在限制，未实现公司行为账务；不输出回测有效性结论。

`config.json` 的 `simulation.symbols_per_cycle` 控制每轮核验数量；行情刷新、费用、手数及回撤防线复用项目配置。

## 全A股共同观察期（2026-11-12更新）

用户指定观察期从2026-11-11开始，2027-05-11复核。母池以沪深北交易所官方普通A股名单为准；
2026-11-12核验5580只，ST、停牌、无分红、新股等不从母池提前删除，按各策略实际证据和交易限制判定。
第七策略按完整母池轮转，不再只跟踪涨停池；每轮限速只控制处理批次，不截断母池。
切换之前的成交保留并标注原范围，缺失的全市场历史不得补造；账户原始created_at不改为昨天。
全市场范围不是收益承诺，证据不足必须等待；不能把数据不足伪装成已证明不符合条件。
