# WP4 性能与可观测性运行手册

## 1. 适用范围

本手册用于本地或 CI 的隔离性能基线，以及 Prometheus 指标出口检查。脚本只使用合成请求和临时 SQLite 数据库，不应对生产地址执行。

## 2. 执行性能门禁

```powershell
pnpm performance:baseline
```

或显式指定端口和证据目录：

```powershell
./scripts/performance-baseline.ps1 `
  -Port 18130 `
  -OutputDirectory .local/performance-wp4-iteration-7
```

统一门禁中的显式入口：

```powershell
./scripts/check.ps1 -SkipInstall -IncludePerformance
```

脚本启动隔离 API，执行 300 次短时 liveness 请求和 40 次精确档案查询，校验报告后停止进程。证据包括：

- `performance-report.json`
- `checksums.sha256`
- `api.stdout.log`
- `api.stderr.log`
- `performance-runtime.db`（本地临时合成数据，不上传为发布制品）

## 3. 手工检查指标

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/v1/metrics
```

必选指标：

- `password_detective_http_requests_total`
- `password_detective_http_request_duration_seconds`
- `password_detective_http_requests_active`
- `password_detective_dependency_up`
- `password_detective_worker_queue_depth`
- `password_detective_process_uptime_seconds`

当 `OBSERVABILITY_METRICS_ENABLED=false` 时，指标入口返回 404。生产环境还必须通过网络策略限制抓取来源；不得依赖指标接口承载用户认证。

## 4. 门禁阈值

| 工作负载 | 阈值 |
|---|---|
| liveness 短时负载 | 目标 100 QPS，实测至少达到 80%，P95 ≤ 250 ms，错误率 ≤ 1% |
| 精确档案查询 | 正常负载目标 10 QPS，实测至少达到 80%，P95 ≤ 500 ms，错误率 ≤ 1% |
| 指标出口 | 六类必选指标存在，路由标签规范化，请求号与完整指纹不导出 |

阈值回退时不得直接放宽校验器。应先保存失败报告，检查 CPU、数据库连接、日志写入、线程池、Redis 和路由级耗时，再由评审确认是否调整规格。

## 5. 边界

该门禁使用单 API 进程、SQLite 和内存限流，仅证明代码级回归基线。生产放行仍需要 MySQL、Redis、Worker、多实例、真实资源配额、长时间混合负载、告警通知和目标环境验收。
