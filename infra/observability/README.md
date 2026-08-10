# 可观测性

M1 已统一 `request_id` 和 JSON 日志格式。M2/M3 接入业务模块时补充：

- Prometheus API 延迟、错误率、数据库连接池和 Redis 指标；
- Worker 队列积压、重试和失败指标；
- Web JS 错误与桌面崩溃率；
- 不含密码、令牌、完整文件名的结构化日志字段白名单。

## WP4 当前基线

- API 指标出口：`GET /api/v1/metrics`。
- Prometheus 配置：`infra/monitoring/prometheus/`，使用 15 秒抓取和规则评估周期。
- 告警规则：`infra/monitoring/prometheus/alerts/password-detective.yml`，7 条低基数规则。
- Grafana 仪表盘：`infra/monitoring/grafana/dashboards/password-detective-overview.json`，6 个基础面板。
- Compose 覆盖层：`infra/monitoring/docker-compose.monitoring.yml`，必须显式启用 `monitoring` profile。
- Alertmanager：`infra/monitoring/alertmanager/alertmanager.yml`，启用低基数分组和 resolved Webhook。
- 合成通知网关：`scripts/alertmanager_receiver.py`；只用于本地/CI，持久化证据对敏感字段统一脱敏。
- 机器校验：`scripts/verify_monitoring_config.py`、`scripts/verify_alertmanager_evidence.py`、`scripts/verify_worker_backlog_evidence.py`。

监控配置只读取脱敏、低基数指标；不得把请求号、用户标识、邮箱、完整指纹、令牌或密码放入 Prometheus 标签、Grafana变量或告警表达式。生产环境还需要独立凭据、网络白名单、正式通知提供商认证/TLS、值班回执、静默/升级策略和目标环境验收。
