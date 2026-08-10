# WP4 监控与告警运行手册

## 1. 适用范围

本手册覆盖 API 指标出口、Prometheus 抓取、Grafana 只读仪表盘和 Worker 默认 Celery 队列积压演练。所有脚本默认使用隔离 Compose 项目、合成值和非默认端口，不得直接指向生产环境。

## 2. 静态校验

```powershell
pnpm monitoring:config
```

或使用 API 虚拟环境：

```powershell
apps/api/.venv/Scripts/python.exe scripts/verify_monitoring_config.py --write-checksums
```

校验器会检查：

- Prometheus 仅抓取 `api:8000/api/v1/metrics`；
- 7 条告警规则均有 severity、runbook 和低基数表达式；
- Grafana datasource、dashboard provisioning 和 6 面板仪表盘完整；
- 规则与仪表盘不包含请求号、用户标识、邮箱、指纹、令牌或秘密字段。

官方语法门禁：

```powershell
docker run --rm --entrypoint promtool `
  -v "${PWD}/infra/monitoring/prometheus:/etc/prometheus:ro" `
  prom/prometheus:v2.55.1 check config /etc/prometheus/prometheus.yml
```

## 3. 启动监控覆盖层

```powershell
$env:APP_SECRET_KEY = "synthetic-monitoring-stack-secret-20260810"
docker compose -f docker-compose.yml `
  -f infra/monitoring/docker-compose.monitoring.yml `
  --profile monitoring up --build --detach --wait mysql redis api prometheus grafana
```

监控覆盖层仅通过 `monitoring` profile 引入，不会使默认 `docker compose up` 强制拉起 Grafana 或 Prometheus。默认本地凭据只允许开发机使用，生产必须注入独立 Secret 并关闭匿名或弱口令配置。

## 4. Worker 队列积压演练

```powershell
pnpm worker:backlog-drill
apps/api/.venv/Scripts/python.exe scripts/verify_worker_backlog_evidence.py `
  --report .local/worker-backlog-wp4-iteration-8/worker-backlog-report.json `
  --write-checksums
```

演练步骤：

1. 启动 MySQL、Redis、API，不启动 Worker；
2. 通过 Celery 投递 24 个 `observability.noop` 合成任务；
3. 从 `/api/v1/metrics` 确认 `password_detective_worker_queue_depth` 至少为 24；
4. 启动 Worker，确认日志出现 ready；
5. 等待队列回到 0，并写入不含凭据的 JSON 证据。

演练会清理自己的 Compose 项目、卷和网络；失败时会保存去敏的 Compose 状态、API 日志和 Worker 日志。

## 5. 告警处置基线

| 告警 | 首要检查 | 当前处置 |
|---|---|---|
| API target down | API 容器、`/api/v1/health/ready`、端口 | 重启或回滚 API，确认 Prometheus target 恢复 |
| Database/Redis unavailable | 依赖健康、连接池和故障日志 | 按恢复演练手册执行依赖恢复 |
| Worker heartbeat missing | Worker ready 日志、进程和 Redis 心跳键 | 重启 Worker，随后执行队列排空演练 |
| High error/P95 | 路由、依赖、资源和最近提交 | 保留报告，禁止直接放宽阈值 |
| Worker queue backlog | 队列深度、Worker 并发、任务失败/重试 | 先保护下游，再扩容或回滚，记录积压消退时间 |

本轮只提供 Prometheus 规则和 Grafana 展示，不代表已接入 Alertmanager、邮件/Webhook、值班确认或告警恢复签字。
