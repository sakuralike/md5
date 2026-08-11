# WP4 Staging 长时稳定性与 Go/No-Go 运行手册

## 1. 目的与边界

本手册定义 WP4 目标环境准入合同、连接池容量预算、长时混合负载、高可用切换证据和自动 Go/No-Go 决策规则。

当前仓库提供的是**可执行合同和证据模板**，不是已经完成的 staging 验收。只有目标环境实际执行不少于 4 小时、完成 MySQL/Redis 高可用切换并通过全部自动证据校验后，才能形成生产放行结论。

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

入口默认复制 `infra/staging/*example.json` 的合成夹具，因此结果必须是 `evidence_kind=contract-fixture`、`execution_status=not-run` 和 `go_no_go_status=pending-evidence`。目标环境采集器生成的报告必须把 `evidence_kind` 改为 `target-execution`，并提供真实但脱敏的时间线、采样覆盖、资源峰值、切换检查和校验和；校验通过会输出 `go`，但仍不能替代未执行的目标环境证据。

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
2. 触发受控的主节点切换；
3. 记录最后一次成功写入、首次失败、首次恢复和复制追平时间；
4. 校验切换前后合成记录连续性和唯一性；
5. 验证 API、Worker、Scheduler 自动恢复连接；
6. 执行回切或确认新的稳定主节点；
7. 生成 `mysql-ha-failover-report.json`。

默认阈值为 RTO 120 秒、RPO 30 秒。目标环境可收紧；放宽必须修改版本化 profile 并重新执行完整证据链。

## 8. Redis 高可用切换

1. 保持 readiness、限流和 Celery 合成任务运行；
2. 触发 Sentinel、托管服务或等效 HA 切换；
3. 验证 liveness 保持可用，readiness 在依赖不可用时 fail-closed；
4. 验证限流状态、Worker 心跳、任务投递和结果获取恢复；
5. 确认最终队列归零且没有重复业务副作用；
6. 生成 `redis-ha-failover-report.json`。

默认阈值为 RTO 60 秒、RPO 5 秒。目标环境可收紧；放宽必须修改版本化 profile 并重新执行完整证据链。

## 9. 自动 Go/No-Go 决策

复制 [WP4 Staging 自动发布决策记录模板](../templates/wp4-staging-release-decision.md) 形成当次候选版本的脱敏决策记录。

决策模式固定为 `automated-evidence-gate`，不要求任何人员签字。任一必需证据缺失、预算超限、HA 切换失败、存在未接受 P0/P1 风险、回滚未验证或校验和不匹配时，最终结论必须为 `NO-GO`；只有全部自动校验通过时输出 `GO`。

## 10. 故障处理

- 校验器拒绝 profile：先修正参数和容量预算，不允许跳过；
- 长时探针出现连续错误：保留证据、停止放行、按依赖和资源趋势定位；
- MySQL/Redis 切换超过阈值：执行回滚并判定 `NO-GO`；
- 证据含敏感字段：销毁该证据，修复采集器后重新完整执行；
- SHA-256 不匹配：证据视为无效，不允许人工覆盖结论。

## 11. Prometheus 与 HA 平台导出接入

目标环境不得把监控端点、PromQL 查询中的内部标签、认证头、连接串或原始平台事件 ID 写入仓库。平台侧先完成聚合和脱敏，再按以下合同导出：

- 资源文件使用 `staging-prometheus-range-export-v1`，包含 API、Worker、MySQL、Redis 的 CPU/内存、对应运行副本数，以及数据库连接数和 Celery 队列深度共 14 个规范化序列；运行副本数序列必须为大于等于 1 的整数，并与资源序列使用同一时间轴；
- 每个序列保留 Prometheus HTTP API `matrix` 响应形状，但必须预聚合为单序列，并使用与 profile 相同的 15 秒采样周期；
- MySQL/Redis 文件使用 `staging-ha-platform-export-v1`，原始平台事件只能以 SHA-256 摘要关联；
- 三个文件必须共享同一 `execution_group_id`、`evidence_kind` 和受控 UTC 时钟基线。

人工执行命令：

```powershell
./scripts/staging-platform-export-execution.ps1 `
  -ResourceExport <prometheus-resource-export.json> `
  -MysqlExport <mysql-ha-platform-export.json> `
  -RedisExport <redis-ha-platform-export.json> `
  -OutputDirectory .local/staging-target-execution-wp4-iteration-15
```

执行链会先运行字段白名单、敏感信息、时间轴、采样周期、整数指标、HA 模式和执行组校验，再调用通用源物化器和最终证据校验器。任何一步失败都不得手工修改最终摘要绕过；应修复平台导出并重新完整执行。

本地/CI 合同只能使用：

```powershell
pnpm staging:platform-export-contract
```

该命令生成的制品必须保持 `evidence_kind=contract-fixture`、`execution_status=not-run`，不可作为自动 Go/No-Go 决策的目标环境证据。

## 12. 证据包封存与自动决策

完成目标环境的资源趋势和 MySQL/Redis HA 报告后，必须先在受控工作目录执行封存重验，再由单一证据包驱动自动决策。入口为：

```powershell
./scripts/staging-evidence-archive.ps1 `
  -EvidenceDirectory .local/staging-target-execution-wp4-iteration-16 `
  -OutputDirectory .local/staging-evidence-archive-wp4-iteration-16 `
  -CandidateCommit <approved-commit-sha>
```

封存器会重新验证六个主证据文件、`checksums.sha256`、`source-checksums.sha256`、执行组、执行标识、profile 摘要、来源摘要和目标执行适配器边界，并生成：

- `staging-evidence-archive-manifest.json`；
- `staging-evidence-archive-manifest.sha256`；
- `staging-evidence-archive.zip`；
- `staging-evidence-archive.zip.sha256`。

目标执行必须提供 40 或 64 位候选提交 SHA；`contract-fixture` 不得携带候选提交，也不得进入自动发布决策。归档 ZIP 只包含脱敏证据、来源 checksum 摘要和封存清单，不包含原始平台导出、端点、凭据、密码、令牌或逐条业务数据。

只有 `target-execution` 且 `handoff_status=ready-for-release` 的封存包才能进入自动决策；封存器与证据校验器在所有资格条件满足时输出 `go`，无需人员签字。

本地/CI 合同入口：

```powershell
pnpm staging:evidence-archive-contract
```

该入口必须保持 `contract-sealed / blocked-by-contract-fixture / not-run / pending-evidence`，不能作为真实 staging 或 HA 验收证据。

## 13. 部署后 Staging 冒烟

部署完成后可使用统一入口验证直接 HTTP Staging，不要求域名或 HTTPS：

```powershell
pnpm staging:smoke -BaseUrl http://<staging-ip>:8000 -WebUrl http://<staging-ip>:5173 -AdminUrl http://<staging-ip>:5174
```

该入口检查 API liveness/readiness、数据库和 rate-limit 就绪、Web/Admin 页面标题、两端 `/api/` 代理，以及唯一合成账号的注册、登录和个人资料读取。它只代表部署后 smoke 通过，不会生成 `target-execution`，也不会替代 4 小时资源趋势、MySQL/Redis HA 切换或自动 Go/No-Go 决策。

若只检查页面和服务，不创建合成账号，可追加 `-SkipAuth`。


## 14. Staging 监控栈预检

监控栈使用 Staging 专用配置，并将管理端口限制在服务器 loopback：

```powershell
docker compose `
  -f docker-compose.yml `
  -f docker-compose.staging.override.yml `
  -f infra/monitoring/docker-compose.monitoring.yml `
  -f infra/staging/docker-compose.staging.monitoring.yml `
  --profile monitoring up -d alert-receiver alertmanager prometheus grafana
```

通过 SSH 本地端口转发访问，不要求域名或 HTTPS，也不得把 `3000`、`9090`、`9093`、`18081` 改为公网监听：

```powershell
ssh -N `
  -L 19090:127.0.0.1:9090 `
  -L 13000:127.0.0.1:3000 `
  -L 19093:127.0.0.1:9093 `
  -L 18082:127.0.0.1:18081 `
  <staging-user>@<staging-host>

pnpm staging:monitoring-smoke `
  -PrometheusUrl http://127.0.0.1:19090 `
  -GrafanaUrl http://127.0.0.1:13000 `
  -AlertmanagerUrl http://127.0.0.1:19093 `
  -AlertReceiverUrl http://127.0.0.1:18082 `
  -Environment staging
```

该 smoke 只验证监控组件可用、API target 为 `up` 且标签正确。它不证明 4 小时采样覆盖、资源阈值、HA 切换或审批完成。

## 15. 目标主机资源观测

在 Staging 部署目录内执行按需观测，不需要新增公网端口或 Docker socket sidecar：

```bash
python3 scripts/collect_staging_resource_observation.py \
  --compose-file docker-compose.yml \
  --compose-file docker-compose.staging.override.yml \
  --duration-seconds 300 \
  --sample-interval-seconds 15 \
  --api-metrics-url http://127.0.0.1:8000/api/v1/metrics \
  --output .local/staging-resource-observation/resource-observation.json

python3 scripts/verify_staging_resource_observation.py \
  --input .local/staging-resource-observation/resource-observation.json \
  --output .local/staging-resource-observation/resource-observation-verification.json \
  --write-checksums
```

Windows 或已安装 PowerShell 的执行环境可使用：

```powershell
pnpm staging:resource-observation `
  -ComposeFiles docker-compose.yml,docker-compose.staging.override.yml `
  -DurationSeconds 300 `
  -SampleIntervalSeconds 15
```

如需资源趋势预采集，可把 `DurationSeconds` 提升到 `14400`。但该入口始终输出 `observation-only`，不会收集四类业务探针窗口、单 Worker 丢失/恢复或 HA 切换，因此不得改名或直接送入 `target-execution`。完整目标执行必须由下一轮长时会话编排器合并业务探针、资源样本和故障事件后生成。

## 16. 长时稳定性会话编排

目标主机必须从部署目录运行以下入口，使资源采样、四类合成探针和单 Worker 丢失/恢复共享同一时间线：

```bash
python3 scripts/run_staging_stability_session.py \
  --compose-file docker-compose.yml \
  --compose-file docker-compose.staging.override.yml \
  --profile infra/staging/readiness-profile.example.json \
  --duration-seconds 14400 \
  --probe-interval-seconds 1 \
  --probe-window-seconds 300 \
  --resource-sample-interval-seconds 15 \
  --worker-count 3 \
  --worker-loss-after-seconds 3600 \
  --worker-loss-duration-seconds 60 \
  --output-directory .local/staging-stability-session \
  --request-target-execution
```

Windows/PowerShell 入口：

```powershell
pnpm staging:stability-session `
  -ComposeFiles docker-compose.yml,docker-compose.staging.override.yml `
  -DurationSeconds 14400 `
  -ProbeWindowSeconds 300 `
  -ResourceSampleIntervalSeconds 15 `
  -WorkerCount 3 `
  -WorkerLossAfterSeconds 3600 `
  -WorkerLossDurationSeconds 60 `
  -RequestTargetExecution
```

执行器会先记录原 Worker 数量，要求 `--worker-count` 与 profile 一致，完成扩容后立即生成拓扑容量预检；随后在探针运行期间停止一个 Worker，再启动同一实例并确认恢复。`finally` 阶段恢复原数量。资源采集器会在每个采样点重新发现运行实例，因此 `3 -> 2 -> 3` 期间不会因已停止容器缺少 Docker stats 而中断。

`--request-target-execution` 不是强制放行开关。只有实际目标拓扑、数据库连接容量、持续时间、采样覆盖、四类操作量/错误/P95、Worker 事件、资源阈值和队列清零全部通过时，输出才会升级为 `target-execution`；否则必须保持 `target-observation / observation-only`。运行失败或资格未通过时禁止手工改写证据状态。

CPU 阈值按每个样本的服务聚合 CPU 除以该样本实际运行副本数计算，口径为 `per-running-replica-average`；内存保留服务聚合值，口径为 `service-aggregate`。每个样本必须记录副本数。2026-08-11 的 77 秒校准确认三 Worker 聚合 CPU `196.35%` 应归一化为 `65.45%`，而单 API 的 `98.63%` 仍真实超限。该会话因时长、操作量、API 副本数和 API CPU 未通过而保持观测状态。


## 17. 目标拓扑与容量预检

正式会话前，在 Staging 部署目录执行：

```bash
python3 scripts/staging_topology_preflight.py \
  --compose-file docker-compose.yml \
  --compose-file docker-compose.staging.override.yml \
  --profile infra/staging/readiness-profile.example.json \
  --output .local/staging-topology-preflight/topology-preflight.json
```

Windows/PowerShell 入口：

```powershell
pnpm staging:topology-preflight `
  -ComposeFiles docker-compose.yml,docker-compose.staging.override.yml `
  -OutputPath .local/staging-topology-preflight/topology-preflight.json
```

预检必须确认：

1. API、Worker、Scheduler 实际运行副本与 profile 精确一致；默认目标为 `2 / 3 / 1`。
2. MySQL、Redis 至少各有一个运行实例。
3. API、Worker、Scheduler 的全部客户端进程乘以 `pool_size + max_overflow` 后，不超过扣除保留连接并应用利用率上限后的允许预算。
4. 输出不得包含容器名、容器 ID、连接串、端点或秘密值。

2026-08-11 的 Staging 实测为 `1 API + 3 Worker + 1 Scheduler + 1 MySQL + 1 Redis`，请求连接 `110`、允许 `136`、剩余 `26`。容量通过，但 API 少一个副本，因此不得进入目标执行。

当前根 Compose 将 API 固定发布到 `${API_PORT:-8000}:8000`，同一主机直接 `--scale api=2` 会产生宿主机端口冲突。正式执行前必须提供 Staging 专用多副本 overlay：API 副本仅暴露容器内部端口，由 loopback 反向代理或负载均衡提供唯一探针入口；Prometheus 也必须覆盖两个 API 实例。不得通过降低 profile 副本数或手工修改预检结果绕过该门禁。


## 18. API 双副本与 loopback 代理部署

Staging 同机双 API 必须叠加 `infra/staging/docker-compose.staging.api-ha.yml`。根 Compose 保持本地开发默认值；overlay 使用 `!reset` 取消 API 宿主机端口，并由 `api-proxy` 独占 `127.0.0.1:${API_PORT:-8000}`。本轮不配置域名或 HTTPS。

Linux 目标主机示例：

```bash
export STAGING_API_IMAGE=password-detective-api:staging-candidate
export COMPOSE_PROJECT_NAME=password-detective-staging

COMPOSE_FILES=(
  -f docker-compose.yml
  -f docker-compose.staging.override.yml
  -f infra/staging/docker-compose.staging.api-ha.yml
  -f infra/monitoring/docker-compose.monitoring.yml
  -f infra/staging/docker-compose.staging.monitoring.yml
)

docker compose "${COMPOSE_FILES[@]}" build api
docker compose "${COMPOSE_FILES[@]}" up -d mysql redis
docker compose "${COMPOSE_FILES[@]}" run --rm api alembic upgrade head
docker compose "${COMPOSE_FILES[@]}" --profile monitoring up -d \
  --scale api=2 --scale worker=3 \
  api api-proxy worker scheduler alert-receiver alertmanager prometheus grafana
```

顺序不可交换：先构建候选镜像，再启动依赖并一次性迁移，最后启动两个 API 副本。禁止恢复根 Compose 中 API 的固定端口，也禁止让每个 API 副本自行执行 Alembic。

PowerShell 客户端通过 SSH loopback 转发后执行组合 smoke：

```powershell
pnpm staging:api-ha-contract

pnpm staging:api-ha-smoke `
  -ApiProxyUrl http://127.0.0.1:8000 `
  -PrometheusUrl http://127.0.0.1:9090 `
  -GrafanaUrl http://127.0.0.1:3000 `
  -AlertmanagerUrl http://127.0.0.1:9093 `
  -AlertReceiverUrl http://127.0.0.1:18081 `
  -ExpectedApiReplicas 2 `
  -ComposeFiles docker-compose.yml,docker-compose.staging.override.yml,infra/staging/docker-compose.staging.api-ha.yml,infra/monitoring/docker-compose.monitoring.yml,infra/staging/docker-compose.staging.monitoring.yml
```

验收必须同时满足：

1. 代理 readiness 返回 `ready / database=ok / rate_limit=ok`；
2. 拓扑预检精确观察到 `2 API + 3 Worker + 1 Scheduler`；
3. Prometheus `service=api` active target 恰好为 2，且两者均为 `up`；
4. 连接池预算和目标依赖检查通过；
5. 先执行 75 秒以上短时资源校准，API 每运行副本平均 CPU 不超过 profile 阈值，再启动不少于 4 小时的正式会话。

若 SSH 报告主机身份变化，必须停止部署，通过可信渠道确认新主机密钥后再更新 `known_hosts`；禁止使用 `StrictHostKeyChecking=no` 或静默删除旧记录绕过验证。
