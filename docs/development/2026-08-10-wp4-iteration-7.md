# WP4 第 7 次开发迭代：性能基线与可观测性出口

- 日期：2026-08-10
- 工作包：WP4 / M5 安全、恢复、性能与可观测性准入
- 本轮目标：把精确查询 P95、短时 100 QPS、请求关联和基础运行指标收口为可重复执行、可机器校验、可由 CI 保存的提交级证据。

## 已完成

### 1. 低基数 Prometheus 指标出口

新增 `core/observability.py` 与 `GET /api/v1/metrics`，导出：

- HTTP 请求总量、进行中请求数和按规范化路由聚合的耗时直方图。
- Database、Redis、Worker 可用性 Gauge。
- Celery 默认队列积压 Gauge。
- API 进程运行时长。

指标标签只包含 HTTP 方法、路由模板、状态码、依赖名称和直方图边界。未匹配路径统一记为 `__unmatched__`；请求号、完整指纹、用户 ID、对象 ID、异常正文、密码、令牌和 Cookie 不进入指标。

### 2. 请求关联与结构化日志

- `RequestContextMiddleware` 使用 `ContextVar` 管理请求生命周期内的 `request_id`，合法的 `X-Request-ID` 继续原样回显，无效值由服务端替换。
- HTTP 完成日志采用 JSON 字段输出 `event/method/route/status_code/duration_ms/request_id`。
- 结构化字典日志在 Formatter 和 Filter 两层执行敏感字段脱敏。
- Worker 在启动和 Celery 心跳时向 Redis 写入 90 秒 TTL 的最小心跳键，正常关闭时清理；API 指标采集只读取心跳存在性和默认队列长度。

### 3. 性能与可观测性门禁

新增：

- `scripts/performance-baseline.ps1`：启动隔离 SQLite/内存限流 API，执行负载，随后停止进程。
- `scripts/performance_probe.py`：执行短时 100 QPS liveness 和精确档案查询基线，并检查指标、路由标签与请求号边界。
- `scripts/verify_performance_evidence.py`：校验固定 `performance-baseline-v1` 结构、P95、错误率、吞吐比例、指标集合和敏感数据约束。
- `scripts/tests/test_verify_performance_evidence.py`：覆盖正常报告、P95 回退和敏感高基数字段拒绝。
- `scripts/check.ps1 -IncludePerformance` 与 `pnpm performance:baseline`。
- GitHub Actions 独立 `performance` 作业和 30 天提交级证据制品。

## 本地真实基线

证据目录：`.local/performance-wp4-iteration-7/`

| 工作负载 | 请求量 | 目标/实测吞吐 | P95 | 错误率 | 结果 |
|---|---:|---:|---:|---:|---|
| Liveness 短时 100 QPS | 300 | 100 / 99.808 QPS | 37.308 ms | 0% | 通过 |
| 精确档案查询正常负载 | 40 | 10 / 10.043 QPS | 96.998 ms | 0% | 通过 |
| 可观测性与最小披露 | 6 类指标 | 全部存在 | 请求号回显且不导出 | 无完整合成指纹 | 通过 |

精确查询 P95 低于规格的 500 ms 上限。100 QPS 仅为短时 liveness 能力基线，不代表业务查询、写入混合负载或生产容量结论。

## 当前边界与下一轮入口

本轮关闭单进程隔离环境的首版性能和指标出口，不代表预生产或生产性能验收。仍未关闭：

- MySQL/Redis/Worker 完整 Compose 混合压测和长时间稳定性。
- Prometheus 抓取部署、Grafana 仪表盘、告警规则和告警通知闭环。
- 多实例聚合、OpenTelemetry Trace、日志集中检索和跨服务关联。
- 候选秘密旧密钥读取与轮换演练。

下一轮进入 WP4 第 8 次迭代，优先建立 Prometheus 告警规则、Grafana 最小仪表盘、告警规则静态校验和 Worker 队列积压演练。
