# 系统设计 · 总览

> v0.1 · 2026-06-06 · Phase 0

> ⚠️ **归档的 v0.1 设计草案（2026-06-06）**：当前实现已转向 A 股个人投资系统，本文部分内容（JWT 认证、`users` 表、Alembic 迁移、`/auth` 路由、Claude 主流程等）**未实现或已被替代**。
> 现行事实以 [README](../../README.md)、`/docs`（OpenAPI）和 `backend/app` 代码为准；本文仅作历史设计参考，勿据此接入。

## 一句话

LLM 增强的个人量化研究工作台:LLM 自动 brief → 一键回测 → 纸面交易 → 全程可复盘。

## 目标用户

- 单一个体投资者(MVP 阶段)
- 后期可演化:量化教育、金融科技 B2B SaaS

## 不做的事(MVP)

- 多用户社交 / 协作 / 跟单
- 真实券商对接
- 移动 app
- 微服务架构
- K8s

## 文件导览

- `00-overview.md` 本文件
- `01-architecture.md` 模块、组件、部署架构
- `02-data-model.md` 表设计、索引、迁移策略
- `03-api-contract.md` REST API 草案
- `adr/` 重要技术决策记录(Architecture Decision Records)
