# WP4 多实例稳定性运行手册

## 1. 适用范围

本手册用于验证单 MySQL、单 Redis、单 API、单 Celery Beat 和多个 Celery Worker 的应用级稳定性。默认演练使用 3 个 Worker，并在混合负载期间主动停止、补回一个实例。

本演练不证明 MySQL 或 Redis 集群高可用，也不替代 staging 长时压测、容量规划或生产签字。

## 2. 架构约束

- 周期任务只能由 `scheduler` 服务运行 Celery Beat。
- `worker` 服务不得携带 `--beat`；横向扩展时只增加消费者。
- 每个 Worker 使用自身容器主机名生成摘要心跳键；停止一个实例不得清理其他实例心跳。
- API 只暴露聚合实例数，不暴露容器名或主机名。
- MySQL 连接池默认值为：

| 变量 | 默认值 | 说明 |
|---|---:|---|
| `DATABASE_POOL_SIZE` | 10 | 每个 API/Worker 进程的常驻连接上限 |
| `DATABASE_MAX_OVERFLOW` | 20 | 突发临时连接上限 |
| `DATABASE_POOL_TIMEOUT_SECONDS` | 30 | 获取连接最长等待时间 |
| `DATABASE_POOL_RECYCLE_SECONDS` | 1800 | 连接回收周期；演练使用 300 秒 |

目标环境必须按“实例数 × 每实例连接上限”核算 MySQL `max_connections`，并预留迁移、运维和故障恢复连接。

## 3. 运行命令

```powershell
pnpm stability:multi-instance
python ./scripts/verify_multi_instance_stability_evidence.py `
  --report ./.local/multi-instance-stability-wp4-iteration-11/multi-instance-stability-report.json `
  --write-checksums
```

也可纳入统一门禁：

```powershell
./scripts/check.ps1 -SkipInstall -IncludeStability
```

常用调试参数：

```powershell
pwsh ./scripts/multi-instance-stability-drill.ps1 `
  -WorkerCount 3 `
  -DurationSeconds 120 `
  -ProbeIntervalSeconds 0.2 `
  -KeepEnvironment
```

脚本默认使用 `18150/13318/16381`，会预检端口、使用随机 Compose 项目名并在结束后删除专用容器、网络和数据卷。Windows 非 ASCII 工作区会临时映射 ASCII 盘符以兼容 Docker BuildKit。

## 4. 验收条件

| 检查 | 最低条件 |
|---|---|
| 初始 Worker | 至少 3 个实例心跳 |
| 单实例故障 | 实例数减少 1，Worker 聚合依赖仍为 1 |
| Worker 替补 | 90 秒内恢复到请求实例数 |
| 混合负载 | API、MySQL、Redis、Celery 各至少完成 10 次 |
| 错误 | 四类探测错误数为 0 |
| 延迟回归线 | API/MySQL P95 ≤ 3000 ms；Redis ≤ 1500 ms；Celery ≤ 15000 ms |
| 队列 | 演练结束后深度为 0 |
| 最终服务 | readiness HTTP 200 |

延迟上限是自动化失效保护线，不是产品 SLO。容量结论必须使用目标环境数据另行批准。

## 5. 证据与敏感信息

报告目录包含：

- `multi-instance-stability-report.json`：编排结果、实例变化、队列和混合探测汇总；
- `mixed-load-probe.json`：各探测次数、P95、最大耗时和脱敏错误；
- `checksums.sha256`：主报告 SHA-256；
- `mixed-load-probe.stdout.log` / `stderr.log`：仅用于失败诊断。

报告不得保存数据库连接串、Redis URL、密码、令牌、Cookie、候选秘密、用户标识或真实业务数据。

## 6. 失败处理

1. 先检查报告的 `error_code`、Compose 状态和各服务末尾日志。
2. Worker 数量异常时检查 `password_detective_worker_instances_ready`、Worker `ready` 日志和 Redis 心跳 TTL。
3. Celery 操作失败时确认只有一个 `scheduler`，并检查队列深度和 Worker 日志。
4. MySQL 超时时核对实例数、连接池参数与 `max_connections`，不得只扩大 overflow 掩盖泄漏。
5. Redis 超时时区分网络故障、服务故障和客户端池耗尽。
6. 修复后必须使用全新 Compose 项目和空数据卷重跑，不得手改 JSON 报告。

## 7. staging 长时验收扩展

生产候选环境至少追加：

- 4～8 小时持续混合负载和资源趋势；
- API/Worker 实例滚动替换；
- MySQL 主从或托管高可用切换；
- Redis Sentinel/Cluster 或托管高可用切换；
- 连接数、队列深度、最老任务、CPU、内存、磁盘和慢查询趋势；
- 告警通知、值班响应、回滚和 Go/No-Go 签字。
