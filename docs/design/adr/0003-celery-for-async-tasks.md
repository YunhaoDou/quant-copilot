# ADR-0003: 后台任务用 Celery + Redis,不用 BackgroundTasks 也不用 K8s CronJob

- 状态:已接受
- 日期:2026-06-06

## 背景

回测(几秒到几分钟)和 LLM 调用(10-60 秒)不能在同步 HTTP 请求中处理。需要决定后台任务方案。

## 选项

1. FastAPI `BackgroundTasks`
2. Celery + Redis
3. RQ + Redis(更轻量)
4. K8s CronJob / Job

## 决策

**Celery + Redis**

## 理由

- `BackgroundTasks` 进程内执行,worker 重启会丢任务,生产不可用
- RQ 更轻量但生态弱,Celery 文档资源 10x 多
- K8s 对单人项目过度,Railway 单实例 worker 够用
- Redis 已经在架构里(用作缓存),Celery broker 复用,**不增加新服务**
- Celery 自带重试、scheduled tasks(替代 cron)、监控生态(flower)

## 后果

- worker 单独的 Docker service
- 任务定义在 `app/tasks/`,task 必须用 `.delay()` 或 `.apply_async()` 派发
- 队列分离:`backtest`, `llm`, `sync` 三个队列,worker 可分别扩容

## 何时重新考虑

- 单机 worker 不够,需要分布式调度
- 引入更复杂的工作流(DAG),换 Prefect / Airflow
