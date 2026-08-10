# WP4 恢复演练运行手册

## 目的与边界

本手册用于在**隔离的 Docker Compose 项目和合成数据**中验证 MySQL、Redis 与 Celery Worker 的基础恢复能力。脚本会清空该隔离项目的数据卷，不得把 `-ProjectName` 指向共享、预发布或生产环境。

当前自动演练覆盖：

1. MySQL 逻辑备份、清空、恢复，以及恢复前后合成账号登录验证。
2. Redis 停止期间 API liveness 保持、readiness 失败、限流后端 fail-closed，以及 Redis 重启后的就绪恢复。
3. Worker 停止期间创建隐私导出任务、Worker 重启后完成任务，并重复投递同一任务验证只产生一条就绪审计事件。

Alembic 往返由 `scripts/check.ps1` 和 CI 的 API 作业独立执行；候选秘密密钥轮换、跨节点/跨区域恢复仍不在本轮范围。

## 执行

```powershell
pnpm recovery:drill
python ./scripts/verify_recovery_evidence.py `
  --report ./.local/recovery-wp4-iteration-6/recovery-report.json `
  --write-checksums
```

也可并入统一门禁：

```powershell
./scripts/check.ps1 -SkipInstall -IncludeRecovery
```

默认隔离资源：

- Compose 项目：`password-detective-recovery`
- API：`18120`
- MySQL：`13316`
- Redis：`16379`
- 证据目录：`.local/recovery-wp4-iteration-6/`

当项目路径包含非 ASCII 字符时，脚本会临时使用 `subst` 映射盘符，以兼容 Docker BuildKit；结束后自动解除映射。除非调试，不要使用 `-KeepEnvironment`。`-SkipBuild` 只适用于已经构建当前代码镜像的本地复跑，CI 不使用该选项。

## 验收阈值

| 指标 | 阈值 |
|---|---:|
| MySQL RPO | ≤ 60 秒 |
| MySQL RTO | ≤ 300 秒 |
| Redis RTO | ≤ 120 秒 |
| Worker RTO | ≤ 180 秒 |

证据校验器还要求三项检查全部通过、失败数为 0，并拒绝包含密码、令牌、Cookie、授权头、Secret 或私钥等疑似敏感字段的报告。

## 证据

- `recovery-report.json`：结构化结果、RPO/RTO、状态码和幂等计数。
- `checksums.sha256`：报告 SHA-256。
- `mysql-backup.sql`：仅包含本轮隔离环境合成数据，不得提交到 Git。
- `recovery-drill.log`：本地调试日志，不得提交到 Git。

CI 使用提交 SHA 命名并保留 30 天的 `recovery-evidence-*` 制品。报告和日志不得写入登录凭据、访问令牌、Cookie 或生产配置。

## 失败处理

1. 查看 `recovery-report.json` 的 `error_code` 和脱敏错误摘要。
2. 调试时使用 `-KeepEnvironment`，执行 `docker compose --project-name password-detective-recovery ps` 与 `logs`。
3. 调试完成后执行：

```powershell
docker compose --project-name password-detective-recovery down --volumes --remove-orphans
```

4. 不得用放宽阈值、删除失败检查或保存敏感材料的方式绕过门禁。
