# WP4 Staging 长时稳定性与 Go/No-Go 运行手册

## 1. 目的与边界

本手册定义 WP4 目标环境准入合同、连接池容量预算、长时混合负载、高可用切换证据和 Go/No-Go 审批规则。

当前仓库提供的是**可执行合同和证据模板**，不是已经完成的 staging 验收。只有目标环境实际执行不少于 4 小时、完成 MySQL/Redis 高可用切换并取得全部角色签字后，才能形成生产放行结论。

所有演练只能使用合成数据。证据不得记录密码、令牌、连接串、私钥、Cookie、真实用户数据或个人信息。

## 2. 配置合同

默认合同位于：

```text
infra/staging/readiness-profile.example.json
```

生成并校验准入计划：

```powershell
pnpm staging:readiness-plan
```

或直接执行：

```powershell
./scripts/staging-readiness-plan.ps1
```

输出：

```text
.local/staging-readiness-wp4-iteration-12/
├── staging-readiness-plan.json
└── checksums.sha256
```

`status=contract-valid` 仅说明参数、容量预算、HA 声明、证据路径和审批角色完整；`execution_status=not-run` 与 `go_no_go_status=pending-evidence` 必须保持到真实执行完成。

生成并校验资源趋势与 HA 执行证据合同：

```powershell
pnpm staging:evidence-contract
./scripts/check.ps1 -SkipInstall -IncludeStagingEvidence
```

输出目录为：

```text
.local/staging-evidence-contract-wp4-iteration-13/
├── readiness-profile.json
├── staging-readiness-plan.json
├── resource-trend-report.json
├── mysql-ha-failover-report.json
├── redis-ha-failover-report.json
├── staging-execution-evidence-summary.json
└── checksums.sha256
```

入口默认复制 `infra/staging/*example.json` 的合成夹具，因此结果必须是 `evidence_kind=contract-fixture`、`execution_status=not-run` 和 `go_no_go_status=pending-evidence`。目标环境采集器生成的报告必须把 `evidence_kind` 改为 `target-execution`，并提供真实但脱敏的时间线、采样覆盖、资源峰值、切换检查和校验和；校验通过只会进入 `pending-approvals`，仍不能替代四角色签字。

### 2.1 目标环境采集与 HA 事件适配器

先在目标环境将监控与 HA 平台事件导出为三个版本化源文件：

- `staging-resource-samples-v1`：资源样本、四类探针窗口、Worker 丢失/恢复事件；
- `staging-ha-events-v1`（MySQL）：预检、切换、主节点变化、读写/一致性/幂等与回滚事件；
- `staging-ha-events-v1`（Redis）：预检、切换、主节点变化、限流/Celery/队列与回滚事件。

三个源文件必须共享 `execution_group_id`，标记相同 `evidence_kind`，使用 UTC `Z` 时间戳，并声明采集器名称、版本和观测时钟偏差。不得包含密码、令牌、密钥、Cookie、Authorization、带凭据连接值、真实个人信息或业务原文。

先运行合成合同，确认当前代码能安全处理 4 小时形状的源数据：

```powershell
pnpm staging:target-adapter-contract
./scripts/check.ps1 -SkipInstall -IncludeStagingAdapters
```

该入口输出 `.local/staging-target-adapter-contract-wp4-iteration-14/`，并强制断言摘要仍是 `contract-fixture / not-run`。它不能作为目标环境证据。

目标环境人工执行：

```powershell
./scripts/staging-target-execution.ps1 `
  -ResourceSource <resource-source.json> `
  -MysqlSource <mysql-ha-source.json> `
  -RedisSource <redis-ha-source.json> `
  -OutputDirectory .local/staging-target-execution-wp4-iteration-14
```

物化器根据真实时间戳推导持续时长、采样覆盖、最大采样间隔和 RTO/RPO，并在最终报告中保存源 SHA-256，而不保存逐条原始采样或目标端点。若适配器名称包含 fixture、synthetic、test 或 mock，则 `target-execution` 直接拒绝。

## 3. 默认容量预算

默认 profile 明确固定 Worker 并发为 2，避免 Celery 根据宿主机 CPU 自动扩大进程数。容量计算公式为：

```text
客户端进程数 = API 副本 × API 进程数
              + Worker 副本 × Worker 并发
              + Scheduler 副本
单进程最大连接数 = pool_size + max_overflow
计划最大连接数 = 客户端进程数 × 单进程最大连接数
允许连接数 = floor((MySQL max_connections - 保留连接数) × 最大预算利用率)
```

默认示例：

```text
客户端进程数 = 2 × 2 + 3 × 2 + 1 = 11
单进程最大连接数 = 5 + 5 = 10
计划最大连接数 = 110
允许连接数 = floor((200 - 30) × 80%) = 136
剩余安全余量 = 26
```

若目标环境拓扑、Worker 并发或 MySQL 上限改变，必须先修改 profile 并重新生成计划。任何超预算配置都会被校验器拒绝。

## 4. 执行前检查

1. 候选提交和文件树已冻结，CI 全部成功；
2. staging 使用与生产一致的编排拓扑，但仅装载合成数据；
3. API 至少 2 个副本、Worker 至少 3 个副本、Scheduler 恰好 1 个副本；
4. `CELERY_WORKER_CONCURRENCY` 与 profile 一致；
5. MySQL、Redis 的 HA 模式、RTO/RPO 和回切路径已由运维确认；
6. Prometheus/Grafana 或同等平台可以采集 CPU、内存、数据库连接数、Redis 内存、Celery 队列和应用 P95；
7. 证据目录只允许写入脱敏 JSON、日志摘要和 SHA-256；
8. 回滚版本、回滚命令和验证步骤已经预演。

## 5. 长时稳定性阶段

建议按以下阶段执行，合计不得少于 profile 的 `duration_seconds`：

1. **基线阶段**：确认所有副本、依赖、队列和指标正常；
2. **混合负载阶段**：持续执行 API、MySQL、Redis 与 Celery 合成探针；
3. **单 Worker 故障阶段**：停止一个 Worker，验证服务不中断并只补回缺失 Worker；
4. **稳态观察阶段**：继续采样 P95、错误率、连续错误和资源水位；
5. **队列清空阶段**：停止负载后确认队列归零和最终 readiness 200；
6. **完整性阶段**：生成证据并写入 SHA-256。

短时 CI 的 60 秒演练只能作为回归门禁，不得替代本阶段。

## 6. 资源趋势证据

`resource-trend-report.json` 至少包含：

- 执行开始、结束和实际持续时间；
- 每个服务的采样数、CPU 峰值/P95、内存峰值/P95；
- MySQL 当前连接数、峰值连接数和拒绝连接数；
- Redis 已用内存、连接数和驱逐数；
- Celery 队列深度峰值、最终深度和最长积压时间；
- API/MySQL/Redis/Celery 操作数、错误率、最大连续错误数和 P95；
- 阈值比较结果；
- 不包含任何秘密或业务数据。

## 7. MySQL 高可用切换

执行前必须记录主节点和复制健康摘要，但不得记录连接串或凭据。

1. 保持合成读写探针运行；
2. 触发批准的主节点切换；
3. 记录最后一次成功写入、首次失败、首次恢复和复制追平时间；
4. 校验切换前后合成记录连续性和唯一性；
5. 验证 API、Worker、Scheduler 自动恢复连接；
6. 执行回切或确认新的稳定主节点；
7. 生成 `mysql-ha-failover-report.json`。

默认阈值为 RTO 120 秒、RPO 30 秒。目标环境可收紧，不能无审批放宽。

## 8. Redis 高可用切换

1. 保持 readiness、限流和 Celery 合成任务运行；
2. 触发 Sentinel、托管服务或等效 HA 切换；
3. 验证 liveness 保持可用，readiness 在依赖不可用时 fail-closed；
4. 验证限流状态、Worker 心跳、任务投递和结果获取恢复；
5. 确认最终队列归零且没有重复业务副作用；
6. 生成 `redis-ha-failover-report.json`。

默认阈值为 RTO 60 秒、RPO 5 秒。目标环境可收紧，不能无审批放宽。

## 9. Go/No-Go

复制 [WP4 Staging Go/No-Go 审批记录模板](../templates/wp4-staging-go-no-go.md) 形成当次候选版本的审批记录。

以下四个角色必须分别签字：

- `technical_owner`
- `security_owner`
- `operations_owner`
- `business_owner`

任一必需证据缺失、预算超限、HA 切换失败、存在未接受 P0/P1 风险或任一角色未签字时，最终结论必须为 `NO-GO`。

## 10. 故障处理

- 校验器拒绝 profile：先修正参数和容量预算，不允许跳过；
- 长时探针出现连续错误：保留证据、停止放行、按依赖和资源趋势定位；
- MySQL/Redis 切换超过阈值：执行回滚并判定 `NO-GO`；
- 证据含敏感字段：销毁该证据，修复采集器后重新完整执行；
- SHA-256 不匹配：证据视为无效，不允许人工覆盖结论。
