# ADR-0001: 选用 monorepo

- 状态:已接受
- 日期:2026-06-06

## 背景

需要决定项目代码组织方式:monorepo(单仓库容纳前后端 + 共享类型)还是 polyrepo(前后端各自独立仓库)。

## 决策

选用 **monorepo**:`quant-copilot/{backend, frontend, shared, docs}`

## 理由

- 单人开发,polyrepo 的 CI / version sync 开销没有收益
- 共享 TypeScript 类型(由 OpenAPI 生成)在 monorepo 里更简单
- 一次 PR 改前后端,review 一目了然
- 项目体量小,monorepo 工具(Turborepo)都不必要

## 后果

- 前后端共用一份 git history
- CI 用 `paths` 过滤实现单边触发
- 部署时分别从 `backend/` 和 `frontend/` 子目录读取

## 何时重新考虑

- 引入第二个前端(iOS / 原生客户端)
- 团队 ≥ 3 人,前后端不同 owner
