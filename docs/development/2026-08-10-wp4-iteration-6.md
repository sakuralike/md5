# WP4 第 6 次开发迭代：MySQL、Redis 与 Worker 恢复演练

- 日期：2026-08-10
- 工作包：WP4 / M5 安全、恢复、性能与可观测性准入
- 本轮目标：把恢复要求从文档步骤收口为可重复执行、可机器校验、可由 CI 保存证据的真实故障演练。

## 已完成

### 1. 隔离恢复演练

新增 `scripts/recovery-drill.ps1`，使用独立 Compose 项目、独立端口和唯一合成账号执行：

- MySQL `mysqldump` 逻辑备份、停止 API/Worker、清空数据库、确认表数为 0、恢复备份、重启服务并验证原合成账号可登录。
- 停止 Redis 后确认 `/health/live` 仍为 200、`/health/ready` 返回 503 `health.redis_unavailable`、认证限流返回 503 `rate_limit.backend_unavailable`；重启 Redis 后 readiness 恢复为 200。
- 停止 Worker 后创建隐私导出任务，重启 Worker 后等待任务进入 `ready`；重复投递相同任务后，`privacy.export.ready` 审计事件仍严格为 1 条。

Compose 对外端口改为可配置且默认值不变，避免与现有本地 API/Web/Admin 冲突。脚本还兼容 Windows 非 ASCII 项目路径的 BuildKit 构建。

### 2. Worker 容器可恢复性修复

真实演练首次暴露两个容器问题：

- Worker 未挂载 `DESKTOP_UPDATE_STORAGE_PATH`，隐私导出任务因目录无写权限失败。
- Celery Beat 默认在只读工作目录创建 `celerybeat-schedule`，产生权限错误。

`docker-compose.yml` 已为 Worker 增加桌面制品卷和显式存储路径，并将 Beat schedule 移至 `/tmp/celerybeat-schedule`。同时新增 `.dockerignore`，避免本地 `node_modules`、虚拟环境和测试制品进入 Docker 构建上下文。

### 3. 证据校验与 CI

- 新增 `scripts/verify_recovery_evidence.py`，固定 `recovery-drill-v1` 结构、三项必选检查、RPO/RTO 阈值、汇总一致性和疑似敏感字段拒绝规则。
- 新增 3 项校验器单元测试；脚本测试全集 16 项通过。
- GitHub Actions 新增 `recovery` 作业，实际执行恢复演练、校验报告并上传 30 天提交级证据。
- `scripts/check.ps1` 新增显式 `-IncludeRecovery`，默认统一门禁不强制执行破坏性 Docker 演练。

## 本地真实演练结果

证据目录：`.local/recovery-wp4-iteration-6/`

| 检查 | 结果 | 实测 |
|---|---|---:|
| MySQL 备份/清空/恢复 | 通过 | RPO 0.648 秒；RTO 17.648 秒；清空后表数 0；合成账号恢复成功 |
| Redis 丢失与恢复 | 通过 | RTO 8.908 秒；liveness 200；outage readiness 503；限流 fail-closed 503；恢复后 readiness 200 |
| Worker 中断与幂等 | 通过 | RTO 31.183 秒；任务 `pending → ready`；Worker ping `pong`；就绪审计事件 1 条 |

全部指标低于本轮阈值：MySQL RPO 60 秒、MySQL RTO 300 秒、Redis RTO 120 秒、Worker RTO 180 秒。报告校验和已生成，凭据、令牌和 Cookie 未写入报告。

## 当前边界与下一轮入口

本轮关闭单节点 Compose 下 MySQL、Redis 和 Worker 的重复恢复证据，不代表生产灾备验收。仍未关闭：

- 候选秘密密钥旧版本读取与轮换。
- 跨节点/跨可用区备份恢复、对象存储恢复和备份保留策略。
- 长时间 Worker 堆积、死信、任务超时和并发重放。
- 性能基线、Prometheus 指标出口、仪表盘和告警运行手册。

下一轮按 WP4 计划进入性能基线与可观测性出口，优先建立查询/写入 P95、短时 100 QPS、HTTP/DB/Redis/Worker 指标和最小披露标签门禁。
