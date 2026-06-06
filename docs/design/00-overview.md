# 系统设计 · 总览

> v0.1 · 2026-06-06 · Phase 0

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
