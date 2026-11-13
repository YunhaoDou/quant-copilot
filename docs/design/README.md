# docs/design（归档）

这里保留 2026-06-06 的 v0.1 设计草案，用于追溯早期产品假设，**不是当前实现的说明书**。

| 文档 | 内容 | 当前状态 |
|---|---|---|
| [00-overview.md](00-overview.md) | 产品定位与里程碑 | 已部分过时（现为 A 股个人投资系统） |
| [01-architecture.md](01-architecture.md) | 高层架构 | 已过时（当前为 FastAPI + cycle 模块 + SQLite 账本 + Next.js 单页 11 视图） |
| [02-data-model.md](02-data-model.md) | 表设计草案 | 部分未实现（`users` 表不存在）；真实模型见 `backend/app/models/` |
| [03-api-contract.md](03-api-contract.md) | API 草案 | 部分未实现（无 JWT/`/auth`/限流）；现行接口见运行后的 `/docs` |
| [adr/](adr/) | 早期架构决策记录 | 历史记录，按日期解读 |

当前事实来源：仓库根 [README.md](../../README.md)、后端运行后的 `/docs`（OpenAPI）、`backend/app` 代码、[docs/sim-protocol.md](../sim-protocol.md)（遗留美股模拟协议）。
