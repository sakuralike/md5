# WP4 第 8 次开发迭代：告警、仪表盘与 Worker 队列积压演练

- 日期：2026-08-10
- 工作包：WP4 / M5 安全、恢复、性能与可观测性准入
- 本轮目标：把上一轮已存在的 `/api/v1/metrics` 出口接入可复用的 Prometheus/Grafana 运行配置，并用真实 Compose 环境演练 Worker 队列从积压到清空的过程。

## 1. 本轮交付

### 1.1 Prometheus

新增以下提交级配置：

- `infra/monitoring/prometheus/prometheus.yml`：固定抓取 `api:8000/api/v1/metrics`，抓取和规则评估周期均为 15 秒。
- `infra/monitoring/prometheus/alerts/password-detective.yml`：7 条低基数告警规则，覆盖 API 抓取目标、Database、Redis、Worker 心跳、HTTP 5xx、P95 延迟和 Worker 队列积压。
- 告警表达式不使用 `request_id`、用户标识、邮箱、指纹、令牌或秘密字段；告警统一指向 `docs/runbooks/wp4-monitoring.md`。

### 1.2 Grafana

新增最小可审阅仪表盘和 provisioning：

- `infra/monitoring/grafana/dashboards/password-detective-overview.json`
- `infra/monitoring/grafana/provisioning/datasources/prometheus.yml`
- `infra/monitoring/grafana/provisioning/dashboards/dashboards.yml`

仪表盘包含请求速率、HTTP P95、5xx 比例、Worker 队列深度、依赖健康和 API 进程运行时长 6 个面板，使用固定 datasource UID `prometheus`。

### 1.3 Compose 监控覆盖层

新增 `infra/monitoring/docker-compose.monitoring.yml`，通过 `monitoring` profile 启动 Prometheus 和 Grafana，不改变默认 Web/Admin/API 本地启动路径：

```powershell
$env:APP_SECRET_KEY = "synthetic-monitoring-stack-secret-20260810"
docker compose -f docker-compose.yml `
  -f infra/monitoring/docker-compose.monitoring.yml `
  --profile monitoring up --build --detach --wait mysql redis api prometheus grafana
```

本地验证过：Prometheus `/-/ready` 返回 HTTP 200，API target 为 `up`，Grafana `/api/health` 返回 `database=ok`，自动加载 `password-detective-overview` 仪表盘。

### 1.4 Worker 队列积压演练

- `worker.py` 增加不访问业务数据的 `observability.noop` 合成任务，仅用于诊断队列排空，不接收真实凭据或生产对象 ID。
- `scripts/worker-backlog-drill.ps1` 使用独立 Compose 项目和端口，先停止 Worker、投递 24 个合成任务，确认指标观察到队列深度 24，再启动 Worker 并等待深度回到 0。
- `scripts/verify_worker_backlog_evidence.py` 校验演练 schema、告警阈值覆盖、队列确实可见、Worker ready 和队列清空，并生成 SHA-256 校验文件。
- 本机真实结果：enqueue 2.255 秒、drain 7.975 秒，队列深度 `24 -> 0`，状态 `passed`。

## 2. 自动化门禁

| 检查 | 结果 |
|---|---|
| Prometheus/Grafana 静态校验 | 通过，7 条规则、6 个面板 |
| Prometheus `promtool check config` | 通过，7 条规则 |
| API 观测性与监控新增测试 | 7 项通过（含既有 WP4 指标测试） |
| Worker 队列积压演练 | 通过，24 个合成任务排空 |
| 监控 Compose smoke | 通过，Prometheus target up、Grafana dashboard 自动加载 |
| 证据校验与 SHA-256 | 通过 |

统一入口新增：

```powershell
./scripts/check.ps1 -SkipInstall -IncludeMonitoring
```

CI 新增 `monitoring` job，执行静态校验、官方 `promtool` 规则校验、队列演练、证据校验和 artifact 上传。

## 3. 当前边界与下一轮入口

本轮关闭了“监控配置缺失、告警规则无校验、Grafana 无最小仪表盘、Worker 积压无真实演练”四项工程缺口，但不等价于生产告警通知闭环。仍未关闭：

- Alertmanager/邮件或 Webhook 通知、值班确认和告警恢复演练；
- MySQL/Redis/Worker 多实例混合压测、长时间稳定性和容量结论；
- OpenTelemetry Trace、集中式日志检索、跨服务请求关联；
- 候选秘密旧密钥读取与密钥轮换演练；
- 预生产/生产目标环境验收和业务/UAT 签字。

下一轮优先补 Alertmanager 通知路由的静态配置与合成告警通知演练，再决定是否进入 M5 完成度复核。
