# WP4 Alertmanager 通知运行手册

## 1. 适用范围

本手册覆盖 Alertmanager 配置校验、合成 firing/resolved 通知、重复通知抑制和通知证据脱敏。命令只允许用于本地或 CI 隔离环境，不得直接向生产值班渠道发送合成告警。

## 2. 配置校验

```powershell
apps/api/.venv/Scripts/python.exe scripts/verify_monitoring_config.py --write-checksums

docker run --rm --entrypoint amtool `
  -v "${PWD}/infra/monitoring/alertmanager:/etc/alertmanager:ro" `
  prom/alertmanager:v0.27.0 `
  check-config /etc/alertmanager/alertmanager.yml
```

校验结果必须确认：

- Prometheus 目标为 `alertmanager:9093`；
- 分组字段仅为 `alertname/service/severity/environment`；
- Webhook 指向 Compose 内部通知网关；
- `send_resolved` 为 `true`；
- 配置中不包含真实密钥、令牌、邮箱或对象级标签。

## 3. 合成通知演练

```powershell
pnpm alertmanager:drill

apps/api/.venv/Scripts/python.exe scripts/verify_alertmanager_evidence.py `
  --report .local/alertmanager-wp4-iteration-9/alertmanager-report.json `
  --write-checksums
```

通过标准：

1. Alertmanager 和通知网关健康检查均为 HTTP 200；
2. 两次相同 firing 告警只交付一次；
3. resolved 通知交付一次；
4. firing/resolved 的 `delivery_id` 均存在且不同；
5. 原始合成秘密标记未进入报告；
6. 报告包含 `[REDACTED]`，证据校验和 SHA-256 通过。

## 4. 告警处置

| 告警 | 首要动作 | 恢复确认 |
|---|---|---|
| API Target Down | 检查 API 容器、端口、健康检查和反向代理 | target 恢复 `up` 且 liveness/ready 连续成功 |
| Database/Redis Unavailable | 检查依赖容器、连接配置和最近变更 | 依赖指标恢复为 1，业务读写冒烟通过 |
| Worker Heartbeat Missing | 检查 Worker 进程、Redis 和心跳键 | Worker ready，心跳恢复且积压开始下降 |
| High Error Rate/P95 | 检查结构化日志、请求路径和依赖耗时 | 5xx/P95 回落并保持一个评估窗口 |
| Worker Queue Backlog | 检查任务生产速率、Worker 容量和失败重试 | 队列深度回到阈值以下并持续下降 |

## 5. 生产接入前检查

- 将内部合成网关替换为经批准的通知提供商或通知代理；
- 启用 TLS、认证、最小权限和秘密轮换；
- 明确 severity 到值班级别的映射、确认时限和升级路径；
- 验证 firing、resolved、静默、抑制和误报关闭流程；
- 保存目标环境证据和运维负责人签字。
