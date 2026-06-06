# ADR-0002: 时序数据用 Postgres + BRIN,不用 InfluxDB / TimescaleDB

- 状态:已接受
- 日期:2026-06-06

## 背景

`prices` 表预计每年每只股票 250 行,1000 只股票 5 年 = 125 万行。需要决定用专门时序数据库还是 Postgres。

## 决策

使用 **Postgres + BRIN 索引**。

## 理由

- 125 万行对 Postgres 是小数据
- BRIN 索引是为追加型时序数据优化的,索引体积小,扫描快
- 多一个数据库 = 多一份运维 + 多一个 Railway 服务费
- TimescaleDB 是 Postgres 扩展,后期真需要再加,不变结构
- Schema 演进、JOIN、JSON 等都用上,关系型一致性是必要的

## 后果

- 时序表(`prices`, `backtest_curves`)用复合 PK + BRIN 加速
- 如果未来数据量 ≥ 1 亿行,迁移到 TimescaleDB 是平滑的(同 Postgres 协议)

## 何时重新考虑

- prices 表 ≥ 5000 万行
- 查询性能瓶颈集中在 prices 表的时间范围扫描
