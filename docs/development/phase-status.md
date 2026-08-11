# 分阶段开发状态

- 更新日期：2026-08-11
- 当前里程碑：WP4 M5 安全、恢复、性能与可观测性准入
- 当前验收口径：固定 4 小时 Staging 稳定性验证已豁免，不再作为未完成项或发布前置条件；短时可重复回归、部署健康、拓扑/容量、恢复、密钥、回滚和必要的 HA 证据仍有效。
- 最近迭代：[WP4 第 30 次开发迭代：管理端 SMTP 邮件投递工作台](./2026-08-11-wp4-iteration-30.md)（完整本地门禁通过）
- 前次迭代：[WP4 第 29 次开发迭代：完整用户等级系统](./2026-08-11-wp4-iteration-29.md)（完整本地门禁通过）
- 前次迭代：[WP4 第 28 次开发迭代：无外部 KMS 的生产文件型秘密管理](./2026-08-11-wp4-iteration-28.md)
- 前次迭代：[WP4 第 27 次开发迭代：HA 目标能力证据封存绑定与完成度基线校正](./2026-08-11-wp4-iteration-27.md)（2026-08-11 21:26 完整本地门禁通过）
- 前次迭代：[WP4 第 26 次开发迭代：托管 HA 目标能力证明与单节点防提升](./2026-08-11-wp4-iteration-26.md)
- 前次迭代：[WP4 第 25 次开发迭代：HA 执行顺序与正式证据绑定门禁](./2026-08-11-wp4-iteration-25.md)
- 前次迭代：[WP4 第 24 次开发迭代：正式 Staging 长时会话后台控制](./2026-08-11-wp4-iteration-24.md)
- 前次迭代：[WP4 第 22 次开发迭代：自动发布治理与桌面制品合法性](./2026-08-11-wp4-iteration-22.md)
- 更早迭代：[WP4 第 21 次开发迭代：Staging 拓扑容量预检与资源归一化](./2026-08-11-wp4-iteration-21.md)
- 前次迭代：[WP4 第 20 次开发迭代：Staging 长时稳定性会话编排与短时实测](./2026-08-11-wp4-iteration-20.md)
- 更早迭代：[WP4 第 19 次开发迭代：Staging 资源观测采集器与证据边界](./2026-08-11-wp4-iteration-19.md)
- 更早迭代：[WP4 第 18 次开发迭代：Staging 监控栈预检与长时观测入口](./2026-08-11-wp4-iteration-18.md)
- 更早迭代：[WP4 第 17 次开发迭代：Staging 运行冒烟与可复用验收入口](./2026-08-10-wp4-iteration-17.md)
- 更早迭代：[WP4 第 16 次开发迭代：证据包封存与审批交接完整性门禁](./2026-08-10-wp4-iteration-16.md)
- 前次迭代：[WP4 第 13 次开发迭代：资源趋势与 HA 执行证据合同](./2026-08-10-wp4-iteration-13.md)
- 最近迭代：[WP4 第 12 次开发迭代：Staging 长时稳定性准入合同](./2026-08-10-wp4-iteration-12.md)
- 前次迭代：[WP4 第 11 次开发迭代：多实例稳定性与单 Worker 故障收口](./2026-08-10-wp4-iteration-11.md)
- 前次迭代：[WP4 第 10 次开发迭代：候选秘密密钥轮换与回滚闭环](./2026-08-10-wp4-iteration-10.md)
- 前次迭代：[WP4 第 9 次开发迭代：Alertmanager 通知闭环与安全演练](./2026-08-10-wp4-iteration-9.md)
- 前次迭代：[WP4 第 8 次开发迭代：告警、仪表盘与 Worker 队列积压演练](./2026-08-10-wp4-iteration-8.md)
- 前次迭代：[WP4 第 7 次开发迭代：性能基线与可观测性出口](./2026-08-10-wp4-iteration-7.md)
- 前次迭代：[WP4 第 5 次开发迭代：管理员 MFA、再认证与幂等滥用门禁](./2026-08-10-wp4-iteration-5.md)
- 前次迭代：[WP4 第 4 次开发迭代：认证对象边界与浏览器 Cookie 安全门禁](./2026-08-10-wp4-iteration-4.md)
- 前次迭代：[WP4 第 3 次开发迭代：API 动态安全与负向门禁](./2026-08-09-wp4-iteration-3.md)
- 前次迭代：[WP4 第 2 次开发迭代：镜像、Secret 与限期风险豁免门禁](./2026-08-09-wp4-iteration-2.md)
- 前序 WP4 迭代：[WP4 第 1 次开发迭代：安全审计与 SBOM 门禁](./2026-08-09-wp4-iteration-1.md)
- 前序迭代：[WP3 第 11 次开发迭代：Firefox 与 WebKit 跨引擎门禁](./2026-08-09-wp3-iteration-11.md)
- 更早迭代：[WP3 第 10 次开发迭代：剩余业务页面无障碍矩阵收口](./2026-08-09-wp3-iteration-10.md)
- 总体审计：[项目整体完成度审计（2026-08-03 复核）](./2026-08-03-completion-audit.md)（历史审计：[2026-08-02](./2026-08-02-completion-audit.md)）
- 下一阶段：[密码侦探社下一步开发方案（2026-08-08）](../../项目文档/密码侦探社下一步开发方案-2026-08-08.md)

> 完成度百分比是基于当前规格、实施计划、代码、测试和环境门禁的工程估算，不是产品签字或生产放行结论。按照完成定义，目标环境验收、外部门禁或生产演练未完成的里程碑不能标记为完全完成。

## 2026-08-11 WP4 第 30 次迭代补充

- 管理端系统设置新增 SMTP 邮件投递工作台：只读展示部署注入配置，提供 MFA 管理员测试邮件入口和最小披露审计。
- 前后端统一门禁通过；真实 SMTP 服务商连通性、发件域名认证、退信/投诉和最终送达仍属于目标环境验收，不由本地测试冒充。

## 2026-08-11 WP4 第 29 次迭代补充

- 建立独立于积分、信誉和产品角色的用户等级体系：不可变成长流水、可重建等级投影、规则哈希和默认五级目录。
- 每日首次登录、首次验证贡献和有效验证自动累计成长值；候选奖励失效/恢复通过追加补偿事件保持事实可追溯和净值正确。
- 配置发布/回滚会重建全部等级投影并审计数量；服务端执行贡献资格和每日揭示额度，等级升级不会获得审核员或管理员权限。
- Web 展示等级进度、权益和成长流水；Admin 支持等级规则治理并在用户详情展示等级。
- 定向后端 17 项、前端/契约测试和类型检查通过；`pwsh ./scripts/check.ps1 -SkipInstall` 完整本地门禁通过。

## 2026-08-11 WP4 第 24 次迭代补充

- 新增正式 Staging 长时会话控制器，默认以 `14400` 秒、双 API、3 Worker、300 秒探针窗口和 15 秒资源采样启动 target-execution。
- supervisor 脱离 SSH 会话运行，使用独占锁、PID 启动标记和原子状态文件防止重复执行、PID 复用误判和证据目录覆盖。
- 状态文件不保存环境变量或秘密；完成时绑定验证报告 SHA-256，并摘要记录执行资格、持续时间、错误率、覆盖率和最终队列。
- `pnpm staging:formal-session`、7 项单元测试和 `check.ps1 -IncludeStagingSession` 已覆盖本轮入口。
- 目标 Staging 正式会话 `20260811T113110Z-eb710ed0` 已于 2026-08-11 19:31:10（Asia/Shanghai）启动；4 小时窗口结束且确认 `eligible_for_target_execution=true` 后才算关闭，其后继续 MySQL/Redis HA 和证据封存。
## 2026-08-11 WP4 第 23 次迭代补充

- 新增 Staging API HA overlay：API 移除宿主机端口发布，Nginx loopback 代理提供唯一入口，API/Worker/Scheduler 共用同一候选运行镜像。
- 数据库迁移改为扩容前一次性执行，避免两个 API 副本并发执行 Alembic。
- Prometheus 改用 DNS 服务发现两个 API 实例；HA smoke 同时校验代理 readiness、`2 API + 3 Worker + 1 Scheduler` 拓扑和两个健康 API target。
- 本地隔离拓扑与 78 秒短时校准通过：四类操作各 70 次零错误，API 每副本平均 CPU 峰值 `73.335%`，Worker `3 -> 2 -> 3` 恢复耗时 `0.454` 秒。
- 目标 Staging 已完成归档校验、一次性迁移、双 API 扩容、双 target 监控与 78 秒校准；API 每副本平均 CPU 峰值 `49.24%`，四类操作各 70 次零错误。
- 结果为 `target-observation / observation-only`；固定 4 小时窗口已豁免，不再阻塞当前验收。现有 78 秒短时校准可作为回归证据，MySQL/Redis HA 仍按独立目标环境证据处理。

## 2026-08-11 WP4 第 22 次迭代补充

- 发布治理改为 `automated-evidence-gate`：目标执行的完整证据、封存 checksum、风险阈值和回滚检查均通过时自动输出 `go`，不再要求项目人员签字；合成夹具仍只能输出 `pending-evidence`。
- 桌面发布去除签名证书门禁；服务端在上传和发布时重算制品大小与 SHA-256，发布记录必须有合法分发确认和合法性声明，审计保留声明摘要。
- 该变化不影响产品 N2 普通角色变更的双人审批；后者是产品权限治理功能，不是项目发布签字。
- 本轮仍未替代真实 4 小时 Staging、MySQL/Redis HA 切换或 Windows 10/11 实机兼容性验证。

## 2026-08-11 WP4 第 21 次迭代补充

- 新增实际 Compose 拓扑与数据库连接容量预检，目标执行必须证明 `2 API + 3 Worker + 1 Scheduler` 和依赖服务真实运行。
- CPU 统一按每个采样点的运行副本数归一化，内存继续按服务聚合；短时会话和最终资源证据使用同一算法。
- Staging 77 秒校准中，Worker 聚合 CPU `196.35%` 归一化为 `65.45%` 后通过；API 单副本 CPU `98.63%` 仍超限。
- 当前 Staging 实际为 `1 API + 3 Worker + 1 Scheduler`，数据库连接预算请求 `110`、允许 `136`、剩余 `26`。
- 根 Compose 的 API 固定宿主机端口阻止同主机双副本；下一轮先实现内部多副本与反向代理/负载均衡入口，再重跑校准和正式 4 小时会话。

## 2026-08-11 WP4 第 20 次迭代补充

- 四类稳定性探针升级为固定窗口，输出操作量、错误数、最大连续错误和 P95。
- 新增长时会话编排器，合并资源样本、业务探针和单 Worker `3 -> 2 -> 3` 丢失/恢复事件。
- 资源采集器支持每个采样点重新发现运行实例，Worker 瞬时丢失期间仍可连续采样且不暴露容器身份。
- Staging 78 秒短时实测和本地复核通过：四类操作均 70 次、错误率 0%、采样覆盖 100%、Worker 恢复 0.278 秒。
- 会话因持续时间、最小操作量和聚合 CPU 阈值未通过而保持 `observation-only`；下一轮先收口资源阈值口径，再执行正式 4 小时会话与 HA。

## 2026-08-11 WP4 第 19 次迭代补充

- 新增目标主机资源观测采集器，按 Compose 服务聚合 API、Worker、MySQL、Redis 的 Docker CPU/内存。
- 同步采集 MySQL 当前连接数和 Celery 队列深度，输出中不包含容器身份、连接串或秘密值。
- 新增 `staging-resource-observation-v1` 校验器、合同示例、5 项测试、PowerShell/pnpm 入口和统一门禁开关。
- 远端 Staging 30 秒短时观测取得 3 个样本并通过校验；该结果固定为 `observation-only`。
- 下一轮补齐长时四类业务探针窗口和单 Worker 丢失/恢复事件，未满足合同前不得进入 `target-execution`。

## 2026-08-11 WP4 第 18 次迭代补充

- 新增 Staging 专用 Prometheus 配置和 Compose overlay，API 目标固定携带 `environment=staging`。
- Prometheus、Grafana、Alertmanager 和通知接收器默认只绑定 loopback；通知接收器镜像改为精确版本。
- 新增 `pnpm staging:monitoring-smoke`，验证监控组件健康、唯一 API target、Staging 标签和 PromQL `up=1`。
- 远端 Staging 监控栈已启动并通过 SSH 转发 smoke；四个监控端口均未直接暴露公网。
- 本轮不替代 4 小时资源趋势、真实 HA 切换、`target-execution` 或四角色审批。

## 2026-08-10 WP4 第 17 次迭代补充

- 新增 `scripts/staging-smoke.ps1` 和 `pnpm staging:smoke`，统一验证 API liveness/readiness、数据库与限流、Web/Admin 页面和 API 代理。
- 默认使用唯一合成账号完成注册、登录和个人资料读取；脚本不输出密码、访问令牌或用户标识。
- 已对远端 Staging `111.229.195.138` 完成直接 HTTP 冒烟，API、Web、Admin、MySQL、Redis、Worker、Scheduler 均正常。
- 本轮只关闭“部署后最小运行可验证”缺口，不把冒烟结果提升为真实 4 小时目标执行、HA 验收、证据封存或四角色审批。
- 下一轮继续准备并执行可脱敏 Prometheus/HA 导出；真实平台证据不可用时保持 `pending-evidence`。

## 2026-08-10 WP4 第 16 次迭代补充

- 新增 `staging-evidence-archive-manifest-v1`，封存前重验主证据文件、`checksums.sha256`、`source-checksums.sha256`、执行组、执行标识和 profile 摘要。
- 新增确定性证据 ZIP、封存清单 detached SHA-256 和 ZIP detached SHA-256；原始平台导出不进入审批交接包。
- 真实 `target-execution` 必须绑定候选提交 SHA，并拒绝 fixture/synthetic/test/mock 适配器；合同夹具保持 `contract-sealed / blocked-by-contract-fixture / not-run / pending-evidence`。
- 新增 `staging-evidence-archive.ps1`、`staging-evidence-archive-contract.ps1`、10 项测试、`check.ps1 -IncludeStagingArchive` 和独立 CI 合同作业。
- 专项 Ruff、10 项 pytest、`pnpm staging:evidence-archive-contract` 和 `check.ps1 -SkipInstall -IncludeStagingAdapters -IncludeStagingArchive` 统一门禁已通过；真实 4 小时 staging、HA 切换、`target-execution` 和四角色审批仍未完成，本轮不提高生产就绪度。
- 下一阶段仍是在已批准 staging 上执行真实长时会话，封存证据后再进入四角色审批。

## 2026-08-10 WP4 第 15 次迭代补充

- 新增 Prometheus `query_range` 规范导入合同，要求 10 个资源/连接/队列序列完全对齐、使用整秒 UTC 时间戳，并匹配 profile 的 15 秒采样周期。
- 新增 MySQL/Redis HA 平台事件导入合同，只允许脱敏生命周期、durability 和原始事件 SHA-256；原始平台事件 ID、端点、凭据和未批准字段被拒绝。
- 新增人工 `staging-platform-export-execution.ps1`、`staging:platform-export-contract`、14 项正负向测试、统一门禁和独立 CI 作业。
- 本地 4 小时形状合同链和 `check.ps1 -SkipInstall -IncludeStagingAdapters` 统一门禁已通过，并保持 `contract-fixture / not-run`；远端 CI `31429066132` 因 GitHub 未分配 runner 而无步骤失败，不能作为代码失败判定；本地 MVP 与生产就绪百分比不因适配合同完成而上调。
- 下一阶段仍是在已批准 staging 上执行真实 4 小时会话和 MySQL/Redis HA 切换，生成 `target-execution` 并完成四角色审批。

## 2026-08-10 WP4 第 14 次迭代补充

- 新增资源采样与 MySQL/Redis HA 事件源合同，将 UTC 时钟偏差、采样覆盖、Worker 故障、切换生命周期和回滚路径固化为机器输入。
- 新增脱敏物化器，最终报告只保留聚合趋势、来源 SHA-256 和低敏感度 provenance，不保留逐条采样、连接串或目标端点。
- 新增人工 `staging-target-execution.ps1`、合成适配器合同、`-IncludeStagingAdapters` 与独立 CI 作业；合成入口强制保持 `contract-fixture / not-run`。
- 本地已走通 4 小时形状的 961 条资源采样、四类各 10,000 次操作以及 MySQL/Redis HA 事件转换；专项 20 项测试和 `check.ps1 -SkipInstall -IncludeStagingAdapters` 统一门禁通过，但该结果仍是合同夹具，不是目标环境执行。
- 下一阶段必须在已批准 staging 上真实运行不少于 4 小时并完成 HA 切换，形成 `target-execution` 后再进入四角色审批。

## 2026-08-10 WP4 第 13 次迭代补充

- 新增资源趋势报告 schema 与校验器，校验 4 小时窗口、采样覆盖、API/MySQL/Redis/Celery 操作量、P95、错误率、CPU/内存峰值、MySQL 连接预算和 Celery 队列清零。
- 新增 MySQL/Redis HA 切换报告 schema，分别要求读写恢复、限流/Worker 恢复、数据/队列完整性、幂等性、回滚就绪和 RTO/RPO 阈值。
- 新增 `staging:evidence-contract`、`-IncludeStagingEvidence` 与独立 CI 作业；证据包通过 profile SHA-256、敏感字段递归拒绝和文件清单校验。
- 本地当前仅验证合成 `contract-fixture`，结果为 `contract-valid` / `not-run` / `pending-evidence`；真实 `target-execution`、4 小时 staging、HA 切换和四角色签字仍未关闭。
- 下一阶段接入目标环境采集器与 HA 适配器，在人工长时门禁前验证脱敏、时钟、采样覆盖、回滚与证据归档。

## 2026-08-10 WP4 第 12 次迭代补充

- 新增 Staging 准入配置、严格校验器、机器执行计划和 SHA-256 清单，将至少 4 小时混合负载、资源采样、单 Worker 故障、HA 切换和四方审批固化为机器合同。
- Compose 显式固定默认 Worker 并发为 `2`；默认拓扑连接预算为请求 `110`、允许 `136`、余量 `26`，超预算配置直接拒绝生成计划。
- 新增 MySQL/Redis 高可用证据字段、RTO/RPO 阈值、运行手册和技术/安全/运维/业务四方 Go/No-Go 模板；敏感键和值不得进入准入证据。
- 当前已完成的是 `contract-valid` 静态准入合同；实际 4 小时 staging 执行、资源趋势、MySQL/Redis 切换证据和审批签字仍为 `not-run` / `pending-evidence`。


## 2026-08-10 WP4 第 11 次迭代补充

- Worker 心跳改为按实例隔离并新增聚合实例数指标，单个 Worker 停止不再误报整个 Worker 依赖不可用。
- Compose 拆分单独 `scheduler` 与可横向扩展的 `worker`，避免多副本重复运行 Celery Beat；MySQL 连接池参数可配置。
- 新增 3 Worker 隔离稳定性演练、并发 API/MySQL/Redis/Celery 探针、单实例故障与替补恢复、队列清零和证据校验。
- 60 秒统一门禁证据为 API 268、MySQL 272、Redis 279、Celery 270 次，合计 1089 次且零错误；这是单机 Compose 回归，不代表生产容量或数据库/缓存高可用。
- 下一阶段仍需 staging 数小时长时趋势、MySQL/Redis 高可用切换、资源水位与目标环境 Go/No-Go 签字。

## 2026-08-10 WP4 第 10 次迭代补充

- 候选秘密加密支持当前版本写入与最多 8 个历史版本读取，未知版本和认证失败按安全错误拒绝。
- 独立 `CANDIDATE_SECRET_DEDUP_KEY` 保证正向轮换和回滚期间去重标签及数据库唯一约束语义稳定；空配置继续兼容原有 `APP_SECRET_KEY + v1` 数据。
- 新增默认 dry-run 的数据库轮换命令、去重一致性停机保护、正向轮换与回滚合成演练、证据校验器、本地统一门禁和独立 CI 作业。
- 本轮关闭应用层旧密钥读取、当前密钥写入、批量轮换和回滚工程闭环；生产 Secret/KMS 注入、多实例长时稳定性和目标环境签字仍未关闭。

> 2026-08-10 WP4 第 6 次迭代在独立 Compose 项目真实执行 MySQL 备份清空恢复、Redis 故障降级/恢复和 Worker 中断重启/任务幂等；实测 MySQL RPO 0.648 秒、RTO 17.648 秒，Redis RTO 8.908 秒，Worker RTO 31.183 秒。恢复脚本、证据校验器和 CI 作业已建立；跨区域灾备、密钥轮换、性能、可观测性和目标环境仍未关闭。

## 2026-08-10 WP4 第 4 次迭代补充

- `scripts/dast_security_gate.py` 新增两个合成已认证用户的隐私导出读取与会话撤销对象边界检查。
- 新增浏览器刷新 Cookie 属性解析与来源校验检查：`HttpOnly`、`SameSite=Lax`、`Path=/api/v1/web/auth`、不可信 Origin 拒绝、可信 Origin 刷新成功。
- 定向测试 12 项通过；API 全量测试 123 项通过、1 项真实 Redis 条件测试跳过；统一安全门禁与本地 DAST 10/10 通过。
- 本轮只关闭普通用户对象边界和浏览器 Cookie 安全的动态证据，管理员 MFA/再认证、幂等重放、资源消耗和恢复等仍按计划保留。

## 2026-08-10 WP4 第 5 次迭代补充

- `scripts/dast_security_gate.py` 新增管理员 MFA/再认证、幂等 replay/conflict、一次性再认证授权重放和限流 `Retry-After` 四类动态滥用检查；总探针数由 10 项增至 13 项。
- 管理员检查使用隔离数据库内唯一合成用户并通过白盒角色 fixture 授予管理员角色，不新增生产管理员 bootstrap 接口；报告不保存密码、TOTP、令牌或 Cookie。
- `errors.py` 为 `rate_limit.exceeded` 补充标准 `Retry-After` 响应头；API 测试同步验证错误响应头与结构化错误体。
- 定向测试 20 项通过、1 项真实 Redis 条件测试跳过；本地 DAST `13/13` 通过；`./scripts/check.ps1 -SkipInstall -IncludeSecurity` 统一门禁通过。
- 本地功能提交 `eb9fa79`，通过 GitHub API 更新远端等价提交 `4a96db42`；GitHub Actions `31352246919` 的 9 个作业全部通过。
- 管理员 MFA/再认证、幂等重放和限流退避的动态证据已关闭；恢复、性能、可观测性、完整 BOLA、人工渗透和目标环境验收仍未关闭。


## 2026-08-10 WP4 第 6 次迭代补充

- 新增独立 Compose 恢复演练，默认使用 API `18120`、MySQL `13316`、Redis `16379`，结束后销毁专用数据卷。
- MySQL 真实执行逻辑备份、清空和恢复，并用同一合成账号验证数据恢复；实测 RPO 0.648 秒、RTO 17.648 秒。
- Redis 停止期间 liveness 保持 200，readiness 与限流依赖 fail-closed 返回 503；重启后 8.908 秒恢复就绪。
- Worker 停止期间排队隐私导出任务，重启后 31.183 秒完成；重复投递后就绪审计事件仍为 1 条。
- 演练暴露并修复 Worker 制品目录和 Celery Beat schedule 权限问题；新增证据结构/阈值/敏感字段校验及提交级 CI 制品。
- 本轮关闭单节点恢复自动证据；跨区域灾备、候选秘密密钥轮换、性能、可观测性和生产目标环境仍未关闭。

## 总体完成度快照

| 维度 | 工程估算 | 说明 |
|---|---:|---|
| 核心业务与 MVP 功能代码 | 约 98% | M1～M4 主流程、用户等级、N1/N2 安全治理、WP2 原子案件处置与通知、WP3 三引擎核心旅程以及 WP4 发布工程均已形成；剩余功能工作主要是外部通知、实机与目标环境验收 |
| 本地工程与自动化准入 | 约 99% | lint、类型、单元/集成、迁移、构建、安全、恢复、性能、监控、Staging 合同、证据适配、封存和 HA 顺序/能力门禁均已自动化；当前候选提交仍需恢复远端 Hosted CI 绿色运行 |
| 综合研发完成度 | 约 92% | 用户等级系统和本轮验收口径修订后产品代码进一步收口，剩余工作主要集中在真实 HA、通知提供商、Windows 实机/样本和生产恢复演练，不以页面数量或历史计划百分比替代目标证据 |
| 生产上线准备度 | 约 83% | 双 API、三 Worker、监控、恢复、短时稳定性回归与自动证据治理已进入 Staging；文件型 Docker Secrets、独立密钥、加密备份和轮换工程合同已完成，固定 4 小时结论已豁免，真实 MySQL/Redis HA、真实通知、生产恢复/密钥演练与实机兼容性仍未关闭 |

| 里程碑 | 工程估算 | 当前判断 |
|---|---:|---|
| M0 需求、安全与体验基线 | 约 88% | 基线文档和用户 Web 视觉规范已落地，产品参数、责任人和完整跨端原型仍待关闭 |
| M1 工程基础与认证 | 约 95% | 代码与环境门禁完成，主分支保护受 GitHub 私有仓库套餐限制 |
| M2 核心 Web 查询与贡献 | 约 95% | 查询、贡献、用户中心、Web Worker、业务 E2E、安全边界和文件型生产密钥注入工程完成；千万级规模性能与目标服务器密钥切换仍待验收 |
| M3 Windows 桌面验证 | 约 90% | 自动化核心、发布工作台、服务端大小/SHA-256 校验和合法分发声明完成；无需签名证书，Win10/11、约 8 GiB 实物样本和对象存储/CDN 待验收 |
| M4 社区信任与管理闭环 | 约 97% | M4 垂直切片、N2 管理治理、WP2 原子处置/结果通知/SLA/Web 申诉以及浏览器核心 E2E 已完成；真实 SMTP/Webhook 最终送达和目标环境验收待关闭 |
| M5 稳定、合规与发布 | 约 83% | 安全、恢复、性能、监控告警、多实例、Staging 编排、证据适配、封存、自动发布门禁与 HA 顺序/能力门禁完成；正式长时结论、真实 HA、生产恢复/密钥与外部兼容性仍待验收 |

## M0：需求、安全与体验基线

| 交付项 | 状态 | 证据 |
|---|---|---|
| v3.0 规格基线 | 完成 | `项目文档/密码侦探社项目规格说明书-v3.0.md` |
| 17 份架构决策 | 完成 | `docs/adr/` |
| 初始数据流与威胁模型 | 完成 | `docs/threat-model/initial-threat-model.md` |
| 需求测试追踪矩阵 | 持续维护 | `docs/testing/requirements-traceability.md` |
| 产品参数确认 | 部分确认 | 文件型 Docker Secrets 已确定；正式域名、揭示配额、RAR、邮件、云平台和日志属地仍待确认 |
| 页面原型/可运行界面 | 可运行增量 | Web 已覆盖认证、查询、贡献和用户安全；Admin 已覆盖真实仪表盘、认证、候选审核、举报申诉、风险告警、审计查询/详情/导出、用户治理总览、停用/恢复/会话撤销和桌面发布 |

## M1：工程基础与认证

| 模块 | 状态 | 说明 |
|---|---|---|
| 单仓目录、嵌套 Git、配置和开发脚本 | 完成 | 当前项目拥有独立 Git 历史；API/Web/Admin/Desktop/Packages/Infra/Docs 已建立 |
| FastAPI 模块化单体 | 完成 M1 范围 | Core/Auth/Admin/Health/DB/Worker 边界已建立 |
| 数据模型与 Alembic 迁移 | 完成 M1 范围 | 用户、会话、审计、设置、账号令牌、幂等记录及迁移 |
| 注册、登录、刷新轮换、退出和会话管理 | 完成 | Argon2id、重放检测、会话族撤销、浏览器/桌面边界 |
| Redis 限流与持久化幂等 | 完成 M1 范围 | FakeRedis 自动化覆盖；真实 Redis 双客户端分布式限流测试已在本地 Docker 环境通过 |
| 邮箱验证与密码重置基础 | 通道完成 | 哈希一次性令牌、非枚举响应、会话撤销、SMTP STARTTLS/SSL 和纯文本邮件；真实服务商/发件域名与事务 Outbox 待验收 |
| 管理员 TOTP 基础 | 完成 | 加密保存、绑定确认、登录验证、MFA 声明和管理端门禁 |
| Vue 用户端与管理端 | 完成 M1 范围 | HttpOnly 刷新 Cookie、管理端 TOTP 入口、可构建可测试 |
| WPF 桌面端骨架 | 完成 M1 范围 | 本地 SHA-256/MD5 PoC 可构建 |
| Docker Compose | 本地门禁完成 | Docker Desktop WSL 2 引擎已恢复；MySQL 8.4/Redis/API/Worker/Web/Admin 空环境构建、迁移、健康检查和合成注册/登录通过 |
| 托管 CI 与分支保护 | PR/CI 完成，保护受套餐限制 | PR #14 和 PR #15 已建立并通过已提交版本的托管 CI；私有仓库主分支保护被当前 GitHub 套餐拒绝启用 |

### M1 尚未关闭的外部门禁

- [x] 在真实 Redis 环境执行分布式集成测试。
- [x] Docker 从空环境启动，并在 30 分钟内完成注册/登录。
- [x] 开发分支 PR 的托管 CI 实际通过。
- [ ] 配置主分支保护；当前私有仓库套餐返回 403，需升级 GitHub 套餐或将仓库调整为支持该功能的可见性。

M1 代码门禁、本地 Docker/Redis 门禁和 PR 托管 CI 已完成；合入与发布仍受私有仓库主分支保护套餐限制约束。

## M2：核心 Web 查询与贡献

| 模块 | 状态 | 说明 |
|---|---|---|
| 档案/指纹/候选/贡献/积分数据模型 | M2 当前范围完成 | 核心五表加反馈、证据历史、状态事件三表；唯一约束、索引和 Alembic 往返已通过 |
| 候选密码加密与去重 | 生产注入工程完成 | AES-GCM、随机 nonce、版本化密钥、独立 HMAC 去重、`*_FILE` 读取、Docker Secrets、加密备份与轮换合同已完成；目标服务器切换待执行 |
| 完整指纹规范化与精确查询 | 完成首版 | MD5/SHA-1/SHA-256/SHA-512 严格校验；匿名和登录可见性分层 |
| 幂等贡献与重复合并 | 完成首版 | 授权声明、持久化幂等、候选去重、多提交证据、待结算积分及首次验证结算 |
| 密码揭示、配额与审计 | 完成首版 | 仅 verified 可揭示；每日配额、no-store 和无明文审计 |
| Web 本地指纹计算 | 完成首版 | SHA-256/MD5 分块计算、进度、取消、耗时和手工指纹输入 |
| Web 查询/贡献/我的贡献 | 完成首版 | 精确查询、遮挡候选、揭示、复制、授权贡献、社区反馈和贡献列表 |
| 验证证据与状态机 | M2 基础完成 | 单账号唯一有效反馈、不可变历史、IP/安装/账号关联键、自动 verified/quarantined、状态事件和首次积分结算 |
| 性能与 E2E | 待实施 | Web Worker 隔离、断网/超大文件 E2E、千万指纹压测待实施 |

### M2 当前门禁

- [x] 注册用户能完成“本地计算 → 无结果 → 贡献 → 我的贡献查看 pending”的代码闭环。
- [x] 指纹和候选唯一约束、幂等重试、重复候选合并具有自动化测试。
- [x] 候选密码密文存储、独立去重标签、揭示配额和无明文审计具有自动化测试。
- [x] API、Web、Admin、Desktop 统一质量检查通过。
- [x] 两个独立成功反馈自动验证，三个独立失败反馈自动隔离并暂停揭示。
- [x] 反馈修改历史、状态事件和首次验证积分结算具有自动化测试。
- [ ] 使用已验证种子数据完成浏览器 E2E“查询 → 揭示 → 复制 → 审计”。
- [ ] 断网、取消和超大文件场景完成浏览器 E2E 与性能验收。
- [ ] 1,000 万指纹规模查询达到 P95 目标或形成优化计划。
- [x] 文件型 Docker Secrets、独立生产密钥、认证加密备份和候选密钥轮换工程合同通过；外部 KMS 不作为上线前置条件。
- [ ] 在目标服务器完成生产秘密初始化、受控切换、备份恢复演练和轮换演练。

## M3：Windows 桌面验证

| 模块 | 状态 | 说明 |
|---|---|---|
| ZIP/7z 本地验证 | 自动化边界完成 | 可重建的加密 ZIP/7z 合成样本、正确/错误密码、损坏/不支持格式、目录枚举、受控内容读取、超时、取消、大小/条目/展开量/压缩比和路径安全限制 |
| 安装身份与会话 | 恢复流程完成 | 首次启动 P-256 密钥；私钥和桌面令牌使用当前用户 DPAPI 保护；撤销/绑定/密钥冲突后可生成新身份并重新注册；不采集硬件标识 |
| 桌面协议闭环 | 完成首版 | 登录、安装公钥注册、一次性挑战、规范载荷、ECDSA 签名和回执提交 |
| 服务端回执校验 | 完成首版 | 安装撤销、最低版本及结构化升级详情、挑战过期/单次使用、绑定、时钟偏差、签名与重放校验 |
| 证据接入 | 完成首版 | 桌面回执接入 `verification-v2`，同结果可升级 Web 证据来源，独立关联组可触发验证；共享安装/IP 的候选内反馈由 `correlation-v1` 动态限权 |
| 桌面更新发布通道 | 管理闭环完成首版 | 后端稳定/测试通道、MFA 草稿/上传/发布/撤回、制品摘要与大小校验、匿名检查/下载；管理端完成发布列表、草稿创建、上传重试、复核、发布与撤回；桌面启动自动检查并显式打开系统浏览器下载入口 |
| 自动化门禁 | 本地与托管门禁通过 | 后端 M3 专项测试、桌面 11 个安全/样本/更新协议测试、Admin 7 个服务测试通过；MySQL 8.4 空环境与全量升降级往返通过；PR #15 CI 运行 `30745600742` 的 API、Frontend、Desktop、Container Images 全部成功 |

### M3 后续门禁

- [x] 修改回执字段、过期挑战、重复回执、账号切换、安装撤销和时钟异常均被拒绝。
- [x] 安装私钥、访问/刷新令牌使用 Windows DPAPI 保护，不采集主板序列号或 MAC 地址。
- [x] 本地验证要求目录枚举和受控内容读取，并拒绝路径穿越条目。
- [x] 补充可重建的带密码 ZIP/7z 正确与错误密码样本、损坏/不支持格式，以及大小、条目、展开量和高压缩比等价边界自动化矩阵。
- [ ] 在隔离测试磁盘执行接近/超过 8 GiB 的物理样本测试；常规 CI 不创建超大实体文件。
- [x] 完成安装撤销、账号绑定冲突、密钥不一致后的新身份生成/重新注册引导，并提供最低版本升级提示。
- [x] 后端可按通道/平台/架构发布不可变版本清单，错误大小/摘要、草稿和撤回制品均不能被客户端下载。
- [x] 桌面端启动自动检查稳定通道，用户只能显式打开系统浏览器下载入口，不静默下载或执行。
- [x] 管理端具备 MFA 发布列表、草稿创建、制品上传/重试、显式发布和撤回闭环，并在客户端侧校验版本、摘要、签名字段、文件名和大小。
- [x] Docker MySQL 8.4 空环境完成全量迁移、服务健康检查和合成注册/登录；迁移升级兼容缺陷已修复。
- [x] 托管 CI MySQL 8.4 全量升降级往返通过；首轮运行 `30745274582` 暴露外键索引降级顺序问题，修复后 PR #15 运行 `30745600742` 的 MySQL 往返和全部作业通过。
- [ ] 在 Windows 10/11 实机执行桌面 E2E。
- [ ] 在正式签名机完成 Authenticode 签名、证书链/时间戳验证和私钥保护验收。
- [ ] 在对象存储/CDN 和生产反向代理限制下完成大制品上传、下载和缓存策略验收。
- [ ] 为桌面发布等高风险操作补充再次 TOTP、细粒度角色或双人复核策略。

## M4：社区信任、状态机与管理端

### 第 1 次迭代已完成

- 新增 `moderation` 模块、Alembic `20260802_0007` 和 `moderation-v1` 人工状态矩阵。
- MFA 审核员/管理员可按状态、候选/存档 ID 或指纹筛选候选，并查看最小披露证据与状态时间线。
- 人工处置记录操作者、原因码、可选说明、前后状态、`request_id` 和处置时证据快照；持久化幂等保证重复请求不重复写事件。
- Admin 已接入审核队列、详情、时间线和隔离/恢复/通过/拒绝操作；候选秘密不进入前端契约、响应或审计详情。
- 专项测试覆盖普通用户越权、MFA 门禁、秘密字段不披露、重复请求、键冲突、原因/目标不匹配、不可变事件、审计和 rejected 普通反馈锁定。

### 第 2 次迭代已完成

- 新增 `trust_cases`、`trust_case_events` 和 Alembic `20260802_0008`，统一承载候选内容举报与贡献者申诉。
- Web 提供举报/申诉案件中心；查询结果可直接举报候选，被拒绝或隔离的本人贡献可直接发起申诉，用户仅能查看本人案件。
- MFA 管理端提供案件筛选、详情、用户说明、处理结果和不可变事件时间线，并按案件类型限制可选处理动作。
- 举报、申诉和管理状态转换均接入持久化幂等、端点限流、受控原因码、请求号和审计脱敏；案件结论与候选状态转换保持独立审计边界。
- API 46 项通过、1 项真实 Redis 条件测试跳过，覆盖率 84%；Web 9 项、Admin 13 项、Desktop 11 项测试通过。SQLite/MySQL 8.4 全量迁移往返和 Docker Compose 空环境烟测通过。

### 第 3 次迭代已完成

- 新增 `reputation_events`、Alembic `20260802_0009` 和 `reputation-v1`，初始信誉统一为 50；实际增减保存前后分值和引用对象，边界零变化事件仍占用幂等键。
- 候选首次验证时，首位贡献者获得 3 点信誉，有效成功验证者获得 2 点信誉；事件通过用户行锁和引用唯一约束保证幂等，分数限制在 0～100。
- 新增本人积分/信誉私有 API，积分从不可变账本按已入账、待结算和已冲正投影，并汇总贡献和反馈统计。
- Web 新增积分与信誉中心，统一查看积分流水、信誉事件和反馈修订历史，不接受其他用户 ID，也不返回候选秘密。
- 统一门禁通过：API 49 项通过、1 项真实 Redis 条件测试跳过、覆盖率 90%；共享契约 2 项、Web 10 项、Admin 13 项、Desktop 11 项测试通过；前端类型检查/生产构建、SQLite 与 MySQL 8.4 全量迁移往返通过。
- 堆叠 PR #18 已创建；GitHub Actions PR 运行 `30758736599` 与 push 运行 `30758710904` 的 API、Frontend、Desktop 和 Container Images 作业全部通过。

### 第 4 次迭代已完成

- 新增 `reward_adjustment_events`、Alembic `20260802_0010` 和 `reward-compensation-v1`，以状态事件驱动首次贡献/验证奖励资格校正。
- 候选进入隔离、拒绝或待验证时追加负积分/信誉事件，恢复验证时仅恢复原始奖励来源；任何流程都不删除或改写原始奖励。
- 自动与人工状态转换在同一事务内执行校正，人工首次通过候选也会完成原始奖励结算；状态事件和来源唯一约束保证多轮流转与重试幂等。
- 管理端详情新增不可变积分/信誉调整时间线，转换响应和成功提示返回本次实际变化汇总；审计仅记录聚合结果。
- API 52 项通过、1 项真实 Redis 条件测试跳过；共享契约 2 项、Web 10 项、Admin 13 项、Desktop 11 项测试通过。SQLite/MySQL 8.4.11 全量迁移往返和统一门禁通过。
- 堆叠 PR #19 已创建；GitHub Actions PR 运行 `30763022872` 与 push 运行 `30763006406` 的 API、Frontend、Desktop 和 Container Images 作业全部通过。

### 第 5 次迭代已完成

- 新增 `risk_alerts`、`risk_alert_events`、Alembic `20260802_0011` 和 `risk-alert-v1`，在 15 分钟窗口内按当前独立失败组与聚合权重识别失败激增。
- 达到阈值时在反馈证据、自动隔离和奖励校正的同一事务内创建高危告警；同一候选、类型和规则版本只保留一个活跃告警。
- 告警只保存窗口、独立失败数和聚合权重，不保存 IP 网段、安装标识哈希或内部关联键；检测与管理员处置均追加不可变事件。
- MFA 管理端已接入告警筛选、详情、确认、解决、重开、受控结果码、持久化幂等、限流和最小披露审计。
- API 54 项通过、1 项真实 Redis 条件测试跳过；共享契约 2 项、Web 10 项、Admin 16 项、Desktop 11 项测试通过。SQLite/MySQL 8.4.11 全量迁移往返和统一门禁通过。
- 堆叠 PR #20 已创建；GitHub Actions push 运行 `30765953749` 与 PR 运行 `30766125682` 的 API、Frontend、Desktop 和 Container Images 作业全部通过。

### 第 6 次迭代已完成

- 新增 ADR-0014、`correlation` 模块、`evidence_correlation_assessments` 和 Alembic `20260803_0012`。
- `correlation-v1` 在候选范围内按安装标识哈希/IP 网段构建传递关联组；同一组对成功和失败分别只保留最高单条反馈权重。
- `verification-v2` 消费关联降权后的有效权重与独立组数；每次有效反馈材料变化在同一事务内追加不可变聚合快照。
- MFA 候选详情展示脱敏账号/反馈标识、信号类型、组数量和原始/有效权重，不返回原始 IP、安装哈希或关联键。
- API 57 项通过、1 项真实 Redis 条件测试跳过，覆盖率 90.99%；共享契约 2 项、Web 10 项、Admin 16 项、Desktop 11 项测试通过；类型检查、生产构建、SQLite/MySQL 8.4.11 迁移往返、真实 Redis 和 Docker 空环境冒烟通过。
- 堆叠 PR #21 已创建；GitHub Actions push 运行 `30775811539` 与 PR 运行 `30775831810` 的 API、Frontend、Desktop 和 Container Images 作业全部通过。

### 第 7 次迭代已完成

- 新增 ADR-0015、`risk-alert-sla-v1`、Alembic `20260803_0013` 和 `risk_alert_notifications` 事务 Outbox。
- 告警固定首版 15 分钟响应、240 分钟解决目标，保存规则版本、绝对截止时间和首次响应时间；管理队列支持负责人和实时超时筛选。
- 具备 MFA 的活跃 moderator/admin 可作为值班处理人；显式指派、隐式认领、重新开启清空负责人均写入不可变事件并受持久化幂等、限流和审计保护。
- Celery Beat 每 60 秒扫描 SLA、每 15 秒投递待发送通知；检测、指派、响应/解决超时、解决和重开通知按接收人去重并最多尝试 3 次。
- Admin 新增 SLA 徽标、响应/解决截止时间、负责人指派、超时筛选和通知历史；响应与通知不返回邮箱、原始 IP、安装哈希或关联键。
- 统一门禁通过：API 默认环境 59 项通过/1 项真实 Redis 条件测试跳过，真实 Redis 环境 60 项全部通过且覆盖率 90.67%；共享契约 2 项、Web 10 项、Admin 18 项、Desktop 11 项通过。SQLite/MySQL 8.4 全量迁移往返和 Docker Compose 空环境冒烟通过，合成注册/登录耗时约 1.0 分钟。堆叠 PR #22 已创建，GitHub Actions push 运行 `30778810391` 与 PR 运行 `30778846715` 全部通过。

### 第 8 次迭代已完成

- 新增 ADR-0016、`notification-webhook-v1`、Alembic `20260803_0014` 和统一通知网关工厂。
- Webhook 后端强制 HTTPS、至少 32 字符签名密钥、1～30 秒超时，并以规范 JSON、UTC 时间戳和 HMAC-SHA256 筿名投递；成功响应可保存提供商消息 ID。
- 通知记录新增提供商、回执、失败时间和重放审计元数据；第三次失败进入终态，人工重放复用原 Outbox 与去重键并重置为待发送。
- 新增 MFA 投递指标、分页过滤和幂等重放 API；重放要求原因和限流，响应与审计不披露邮箱、Webhook 地址、密钥或原始投递载荷。
- Admin 风险工作台新增投递指标卡、失败队列、告警跳转和手动重放入口；共享契约与服务测试同步扩展。
- 自动化已覆盖三次失败终态、指标/过滤、最小披露、幂等重放、审计原因、规范载荷、签名和提供商回执；堆叠 PR #23 已创建，GitHub Actions push 运行 `30784336062` 与 pull_request 运行 `30784366021` 的四项作业全部通过。

### 第 9 次迭代已完成

- 新增 ADR-0017 和 `smtp` 通知后端，账号验证、密码重置和风险告警可通过统一网关发送 UTF-8 纯文本邮件。
- 支持 STARTTLS、隐式 SSL 和仅限本地测试的明文模式；非本地环境强制认证与传输加密，SMTP 密码使用秘密类型保存。
- 账户邮件只包含一次性令牌和安全提示；风险告警邮件只包含告警 ID、通知类型、严重级别与 UTC 处理时限，不披露候选秘密或证据原文。
- SMTP 接受后返回本地 RFC Message-ID，风险告警复用现有提供商/回执、三次失败终态、指标和幂等重放链路；Message-ID 不解释为最终送达。
- `.env.example`、API/Worker Compose、本地开发指南、规格、计划、模块地图、追踪矩阵和 README 已同步更新，示例只包含合成占位符。
- 统一本地门禁通过：SMTP/Webhook 专项测试 7 项，API 默认环境 67 项通过/1 项真实 Redis 条件测试跳过、覆盖率 91%，真实 Redis 分布式限流测试 1 项通过；共享契约 2 项、Web 10 项、Admin 20 项、Desktop 11 项通过。
- Ruff、前端类型检查/生产构建、桌面 Release 构建、SQLite/MySQL 8.4 全量迁移往返、`docker compose config` 和 Docker Compose 空环境冒烟通过；最终复验合成注册/登录耗时约 7.7 分钟，资源已清理。创建堆叠 PR #24；GitHub Actions push 运行 `30786947956` 与 pull_request 运行 `30786976922` 的 API、Frontend、Desktop 和 Container Images 作业全部通过。

### N1 第 1 次迭代已完成

- 新增本人用户名修改、密码修改和用户 TOTP 生成/确认/停用接口，复用现有用户、会话、审计和幂等模型，无需数据库迁移。
- 密码修改以当前密码作为再认证；已启用 TOTP 的账号必须再次校验动态码；成功后保留当前会话并撤销其他会话族。统一凭据约束在 N1 第 4 次迭代中收口。
- TOTP 明文密钥只在生成响应中返回，不写入审计和幂等响应缓存；停用时清理活跃会话的 MFA 标记。
- Web 账号安全页升级为 Shadcn-Vue/Tailwind 三栏用户中心，覆盖资料、密码、TOTP 和会话管理。
- API 全量 70 项通过/1 项真实 Redis 条件测试跳过；Web 13 项测试、类型检查和生产构建通过。

### N1 第 2 次迭代已完成本地切片

- 新增揭示历史最小披露查询、版本化授权声明、数据导出和账号删除申请状态机。
- 新增 `20260803_0015` 迁移；导出短时凭证一次性下载，删除到期后账号停用/去标识化并保留审计。
- 新增 Web `/account/activity` 与 `/account/privacy` 页面及服务层测试。
- N1 本地切片 API 6 项、Web 全量 15 项、Ruff 和迁移往返通过；真实 MySQL/Redis/Celery、浏览器 E2E、合规参数和生产验收仍待完成。

### N1 第 3 次迭代已完成 Web 认证恢复闭环

- 新增 `/verify-email`、`/forgot-password`、`/reset-password` 和 `/account/profile` 计划入口，复用既有安全 API，不重复创建认证协议。
- 登录页支持 TOTP 验证码；账号资料页显示邮箱验证状态并支持重发验证邮件。
- 一次性验证/重置凭证读取后从地址栏移除，只通过请求体提交，不进入浏览器持久化存储。
- 新增公共认证服务和 4 项服务测试，Web 全量 19 项及统一全仓门禁通过；浏览器 Playwright、真实 SMTP/目标环境仍待后续关闭。

### N1 第 4 次迭代已完成本地切片

- 新增 `reauthentication_grants` 与 Alembic `20260803_0016`，凭据仅保存 SHA-256 摘要，默认 5 分钟过期并绑定当前会话族与精确操作目的。
- 新增 `POST /me/security/reauthenticate`；当前密码必需，启用 TOTP 时还需动态码；响应设置 `Cache-Control: no-store`，签发接口不使用幂等键，避免缓存一次性秘密。
- 密码修改、TOTP 停用和账号删除申请统一消费一次性凭据；消费与业务写入同事务完成，成功后撤销其他未消费凭据。
- 补充跨会话、跨目的、过期、重放、原始令牌不落库和 Web 服务层覆盖；统一门禁通过：API 78 项通过/1 项真实 Redis 条件测试跳过、覆盖率 90%，Web 19 项通过，类型检查、构建、桌面测试、迁移往返和 Compose 配置检查通过。

### N2 第 1 次迭代已完成本地切片

- 新增 MFA 门禁的 `GET /admin/dashboard/summary`，按 1～720 小时窗口聚合查询、命中、贡献和已审计业务操作失败率，并返回候选验证/隔离快照与治理队列积压。
- 有效档案查询新增 `archive.search` 脱敏审计遥测；仅保存算法、命中状态、认证状态、请求号和脱敏 IP 网段，不保存完整指纹或候选秘密。
- Admin 静态仪表盘替换为真实指标卡、治理待办队列、数据生成时间和明确口径说明；共享契约与服务测试已补齐。
- 本轮不新增数据表；管理员危险操作近期再认证、角色变更后端双人复核、审计保留/归档和大规模异步导出继续列为 N2 后续范围。

### N2 第 2 次迭代已完成本地切片

- 新增 MFA 门禁的审计日志分页列表、精确/综合筛选和单条详情；响应补充操作者用户名/角色，但不返回邮箱。
- 新增同步 CSV 导出：单次最多 5000 条、每分钟最多 10 次，使用 UTF-8 BOM、公式注入防护，并写入 `admin.audit.export` 审计。
- 审计详情与导出统一执行服务端递归脱敏、深度/数量/长度限制；列表和详情读取不写审计，避免自递归与无界噪声。
- Admin 审计骨架替换为真实工作台，使用 Shadcn-Vue 基础组件和 Tailwind 毛玻璃表面，覆盖筛选、分页、空态、详情抽屉和下载反馈。
- 本切片无数据库迁移；自动化覆盖普通用户拒绝、MFA、筛选、时间边界、详情缺失、脱敏、导出上限和页面基础渲染。
- 统一门禁证据：API 82 项通过/1 项真实 Redis 条件测试跳过、覆盖率 90%，共享契约 2 项、Web 19 项、Admin 24 项，桌面端 Release 构建与 11 项测试通过；迁移往返、Compose 配置和差异检查通过。

### N2 第 3 次迭代已完成本地切片

- 用户治理从列表升级为详情与状态总览，提供状态、角色、会话数量、风险标记和最近活动信息。
- 服务层补齐用户列表、详情、状态筛选和脱敏映射；Admin 页面保持管理员/服务账号及自身对象只读。
- 本轮无数据库迁移；Admin 27 项专项测试、类型检查和生产构建通过。

### N2 第 6～7 次迭代已完成角色治理本地闭环

- 新增 `role_change_requests` 表、迁移和共享 API 契约，冻结普通角色之间的允许转换矩阵。
- 新增角色变更创建、分页查询、批准和拒绝 API；批准必须由不同管理员复核，并在成功后撤销目标账号活跃会话。
- 复用用户治理一次性再认证，补齐对象保护、状态/角色乐观并发、幂等、原因码和最小披露审计。
- Admin `/role-changes` 工作台已支持状态筛选、分页、加载/空/错误态、选中详情、创建、批准、拒绝和凭据清理；服务、状态控制器和基础渲染测试已补齐。
- 独立角色事件时间线、批量处置、紧急撤权和管理员/服务账号角色治理仍未开放。

### N2 第 12 次迭代已完成 WP1 第五轮与总体验收

- Admin 候选审核页完成 `Badge`、`Button`、`Input`、`Label`、`Select`、`Textarea` 和 Tailwind Mobile-first 迁移，保留筛选、关联证据降权、人工状态迁移、奖励校正及不可变时间线。
- Admin 桌面发布页完成 `Badge`、`Button`、`Checkbox`、`Input`、`Label`、`Select`、`Textarea` 迁移，保留制品校验、上传恢复、发布和撤回安全边界。
- 两张复杂页面分别新增 SSR 基础渲染测试；Admin 当前 21 个测试文件、49 项测试通过。
- 前端规范冻结基线从 2 个 Admin 文件 60 项清零；WP1 累计从 11 个文件 164 项降至 0 项，新增违规为 0，本地工程出口条件已满足。
- Windows PowerShell 5.1 统一门禁通过：API 92 项通过/1 项真实 Redis 条件测试跳过、覆盖率 90%，共享契约 2 项、Web 22 项、Admin 49 项、Desktop 11 项通过；迁移往返、前端 lint/typecheck/test/build、桌面 Release 构建、Compose 配置和 PowerShell 7 语法解析通过。
- 下一轮进入 WP2 账号申诉、案件编排与结果通知；浏览器 E2E、真实通知环境、目标环境验收和生产放行仍单独验收。

### N2 第 10 次迭代已完成 WP1 第三轮

- Admin 登录页完成 `Button`、`Input`、`Label` 迁移，保留密码、可选 TOTP、忙碌态和错误反馈语义。
- Admin TOTP 设置页完成 `Button`、`Input`、`Label` 迁移，配置 URI 使用 Tailwind `break-all`，删除行内样式且不改变密钥短时内存边界。
- 两张页面分别新增 SSR 基础渲染测试；Admin 当前 17 个测试文件、45 项测试通过。
- 前端规范冻结基线删除两张已整改页面，历史欠账从 6 个文件 125 项降至 4 个 Admin 文件 117 项；WP1 仍需关闭候选审核、桌面发布、风险告警和案件处置页面。
- Windows PowerShell 5.1 统一门禁通过：API 92 项通过/1 项真实 Redis 条件测试跳过、共享契约 2 项、Web 22 项、Admin 45 项、Desktop 11 项通过；迁移往返、前端 lint/typecheck/build、桌面 Release 构建和 Compose 配置检查通过。

### N2 第 9 次迭代已完成 WP1 第二轮

- Web 积分/信誉中心完成 `Button`、`Progress` 与 Tailwind 响应式布局迁移，不再使用页面行内进度样式、自定义 `<style>` 或硬编码颜色。
- Web 举报/申诉案件中心完成 `Button`、`Input`、`Label`、`Select`、`Textarea` 迁移，案件状态改用 Tailwind 语义颜色；Shadcn-Vue CLI 新增 Select 组件族。
- 两张页面分别新增 SSR 基础渲染测试；Web 当前 10 个测试文件、22 项测试通过。
- 前端规范冻结基线删除两张已整改页面，历史欠账从 8 个文件 141 项降至 6 个 Admin 文件 125 项；WP1 仍需关闭 Admin 登录、TOTP、候选审核、桌面发布、风险告警和案件处置页面。
- Windows PowerShell 5.1 统一门禁通过：API 92 项通过/1 项真实 Redis 条件测试跳过、共享契约 2 项、Web 22 项、Admin 43 项、Desktop 11 项通过；迁移往返、前端 lint/typecheck/build、桌面 Release 构建和 Compose 配置检查通过。

### N2 第 8 次迭代已完成 WP1 第一轮

- 根工作区、Web 和 Admin 已建立 ESLint 与 `pnpm lint`，并接入 `scripts/check.ps1` 和 GitHub Actions。
- 业务 Vue 规范门禁已冻结历史欠账，禁止新增 `<style>`、行内样式、十六进制颜色和原生表单控件；Shadcn-Vue 生成目录不做业务误报。
- App、首页和注册页完成用户基础流程首批整改；首页新增 SSR 基础渲染测试。
- 历史规范欠账从 11 个文件 164 项降至 8 个文件 141 项；Windows PowerShell 5.1 统一门禁已通过，API 92 项通过/1 项跳过、共享契约 2 项、Web 20 项、Admin 43 项、Desktop 11 项通过。用户案件/信誉和 Admin 复杂页面仍待后续批次清零，因此 WP1 尚未整体完成。
### N2 第 4 次迭代已完成统一本地门禁

- 用户治理新增管理员专用再认证、停用/恢复、会话撤销和结构化原因码。
- 危险操作统一使用当前密码 + TOTP、一次性会话族绑定凭据、`Idempotency-Key`、乐观并发、对象级保护和最小披露不可变审计。
- Admin 工作台新增危险操作确认侧栏，不持久化密码/TOTP/再认证令牌；管理员、服务账号和自身对象保持只读。
- 本轮无数据库迁移；API 89 项测试中 88 项通过、1 项真实 Redis 条件测试跳过，覆盖率 90.46%；共享契约 2 项、Web 19 项、Admin 29 项和桌面端 11 项测试通过；类型检查、构建、Ruff、迁移往返、Compose 配置和差异检查通过。

### 后续范围

| 范围 | 状态 | 说明 |
|---|---|---|
| 证据、反馈、状态事件基础 | 核心完成 | `vote_feedback`、证据历史、状态事件、候选内关联图、动态限权、不可变关联快照和自动晋级/隔离已在 M2/M3/M4 建立；跨候选图谱待后续 |
| 积分与信誉 | 核心完成 | 首次验证结算、账本投影、`reputation-v1`、不可变信誉事件及 `reward-compensation-v1` 撤销/恢复校正已实现；动态信誉权重待实施 |
| 管理处置闭环 | 核心闭环完成 | 候选筛选、证据详情、状态时间线、隔离/恢复/通过/拒绝、用户停用/恢复、会话撤销、普通角色变更申请/双人复核、原因记录、幂等、并发、审计和案件原子处置已实现；批量治理和跨候选图谱属于后续增强 |
| 举报、信誉、申诉和配置 | 核心闭环完成 | 举报/申诉统一案件、账号申诉、指派/重开、原子最终处置、结果通知 Outbox、SLA 升级、信誉/补偿和 Web 账号申诉交互已实现；真实通知服务商和目标环境回调待验收 |
| 异常检测和告警 | 五个垂直切片完成 | `risk-alert-v1`、`correlation-v1`、`risk-alert-sla-v1`、`notification-webhook-v1` 与 SMTP 邮件已实现失败激增、候选内关联降权、MFA 值班指派、签名/Webhook/邮件通知、投递指标、失败队列和幂等人工重放；真实 SMTP 服务商/发件域名、最终送达回调、排班升级链、指标导出和跨候选分析待实现 |
| 安全与权限验收 | 局部自动化完成 | 用户治理已覆盖普通用户拒绝、MFA、对象级保护、并发冲突、幂等重放和最小披露；CSRF/XSS、批量接口资源消耗、角色层级和生产安全扫描待实施 |


### WP2 第 1 次迭代：账号申诉与统一案件主体基线（已完成）

- 统一 `trust_cases` 新增 `account_appeal` 与 `candidate/account/risk_alert` 单一主体约束；历史候选案件回填为 `candidate`。
- 已实现 `POST /trust/account-appeals` 和 `GET /trust/cases/{case_id}`，覆盖服务端派生目标账号、幂等重放/冲突、本人详情、跨账号 404、事件 request_id 和审计最小披露。
- Web/Admin 共享契约和案件列表已兼容账号/候选/风险告警主体；新增 WP2 API 集成测试与 Web 服务层测试。
- 本轮仍未完成独立指派、原子 resolve/reopen、SLA、通知 Outbox、副作用补偿和 Web 账号申诉表单，不能宣称 WP2 或 N3 闭环完成。
- Windows PowerShell 5.1 统一门禁通过：API 94 项通过、1 项真实 Redis 条件测试跳过、覆盖率 90%；共享契约 2 项、Web 23 项、Admin 49 项、Desktop 11 项测试通过；Ruff、前端规范检查、类型检查、生产构建、桌面 Release 构建及 SQLite 全量迁移 `upgrade → downgrade base → upgrade` 通过。

### WP2 第 2 次迭代：案件指派、重开与乐观并发（本轮完成）

- 新增前进迁移 `20260808_0020`：`trust_cases.version` 作为非空版本号；`trust_case_events` 新增负责人前后 ID，并保留历史迁移可回滚性。
- 新增 `POST /admin/trust-cases/{case_id}/assign` 与 `POST /admin/trust-cases/{case_id}/reopen`；两者均要求 MFA、限流、`Idempotency-Key` 和 `expected_version`。指派对象必须是启用状态的审核员/管理员，重开仅允许已解决/已驳回案件并清理负责人和结论元数据。
- 通用 `transition` 进入复核时保留显式负责人，不再承担关闭案件重开；所有管理写操作统一返回版本与负责人快照，冲突返回 `409 trust.case_version_conflict`。
- Admin 案件详情增加版本、负责人指派和专用重开操作；共享契约、服务层测试、API 集成测试和事件/审计最小披露断言已同步。
- 本轮未实现原子 `resolve`、账号/候选状态副作用、奖励/信誉补偿、通知 Outbox、案件 SLA、自动分派和 Web 账号申诉表单；不能宣称 WP2 或 N3 闭环完成。
- 统一门禁实测：API 97 项（96 通过、1 项真实 Redis 条件测试跳过）、覆盖率 93.07%；共享契约 2 项、Web 23 项、Admin 50 项、Desktop 11 项测试通过；Ruff、前端规范检查、类型检查、生产构建、桌面 Release 构建及 SQLite 全量迁移往返通过。

## M5：稳定、合规与发布

| 范围 | 状态 | 说明 |
|---|---|---|
| 系统测试与性能 | 部分实施 | Web/Admin 30 项已在本地 Playwright Chromium、Firefox、WebKit 共 90/90 通过，远端三浏览器矩阵已配置；Windows 10/11 Edge、真实 Safari、真实读屏器、移动实机、混合压测和跨平台像素批准待实施 |
| 安全验证 | 部分实施 | Python/Node 依赖审计、API Bandit SAST、API/仓库 CycloneDX SBOM、三个最终镜像 HIGH/CRITICAL 扫描、仓库 Secret 扫描、限期双人风险接受和提交级 SHA-256 证据已进入 CI；DAST、专项越权/XSS/资源消耗和人工安全测试待实施 |
| 恢复与密钥演练 | 未实施 | 备份恢复、迁移回滚、密钥轮换、Redis 丢失和 Worker 重启演练待实施 |
| 合规与数据治理 | 未实施 | 隐私政策、条款、授权记录、投诉删除和数据保留配置待实施 |
| 发布与运维 | 基础设施骨架 | Docker/CI 基线已有；预生产、监控告警、运行手册、RC、灰度、回滚和联合签字待实施 |

## 2026-08-09 WP3 第 8 次迭代补充：视觉、可访问性与刷新竞争收口

| 需求 | 实现证据 | 自动化证据 | 状态与剩余风险 |
|---|---|---|---|
| Web/Admin 首批结构化视觉基线 | `tests/e2e/support/visual_assertions.ts`、Web/Admin 响应式布局 | Web 登录/首页、Admin 仪表盘/登录页全页 PNG 报告附件、关键区域边界和页面级无溢出断言 | 首批 4 个页面完成；跨平台像素差异批准与更多核心页面待补充 |
| 键盘、错误提示与严重 WCAG 门禁 | Admin 导航/登录页焦点环和实时错误区、Web 登录错误实时区、Web 语义前景色对比度修正 | 登录表单焦点顺序、错误 `role=alert`/`aria-live`、Axe WCAG 2 A/AA 与 2.1 A/AA 严重/关键违规扫描 | 首批页面通过；屏幕阅读器、全部复杂页面和目标浏览器矩阵未验收 |
| 刷新令牌缺失、过期与多标签竞争 | `rotate_refresh_token` 条件更新原子认领、隔离过期/并发刷新会话 | 缺失 Cookie、自然过期、并发仅一次成功、竞争重放拒绝、访问令牌和轮换令牌同族撤销 | SQLite 真实 API 闭环完成；MySQL 目标环境并发验证待执行 |
| WP3 本地统一回归 | `playwright.config.ts`、`tests/e2e/*.spec.ts` | API 身份 11 项、Admin 52 项、完整 25 项 Chromium 旅程及静态检查 | `scripts/check.ps1 -SkipInstall -IncludeE2E` 统一门禁通过；远端 CI `31305403414` 五个作业通过 |

## 2026-08-09 WP3 第 9 次迭代补充：已登录核心页面无障碍与响应式收口

| 需求 | 实现证据 | 自动化证据 | 状态与剩余风险 |
|---|---|---|---|
| Web/Admin 主内容跳转与键盘焦点 | `apps/web/src/App.vue`、`apps/admin/src/App.vue`、`tests/e2e/support/accessibility.ts` | 三条已登录 E2E 首次 Tab 聚焦跳过链接，Enter 后 `#main-content` 获得焦点 | 本地 Chromium 通过；屏幕阅读器和目标浏览器矩阵待验收 |
| Web 安全与隐私移动/桌面视觉门禁 | `web-authenticated-accessibility.spec.ts`、`SecurityPage.vue`、`AccountPrivacyPage.vue` | 1440 × 900 安全页、390 × 844 隐私页；无页面级横向溢出、关键区域边界和全页 PNG 报告 | 本地 Chromium 与 Axe 严重/关键违规为零；跨平台像素批准和中等违规治理待补充 |
| Admin 用户治理与角色审批可访问性 | `admin-authenticated-accessibility.spec.ts`、`UserGovernancePage.vue`、`RoleChangesPage.vue` | 桌面治理页、移动审批页；SelectTrigger 显式名称、主内容跳转和 Axe 门禁 | 本地 Chromium 与 Axe 严重/关键违规为零；复杂写操作键盘全流程和屏幕阅读器待验收 |
| 错误/成功反馈实时语义 | Web/Admin 页面 `role`、`aria-live` 属性 | 页面结构和浏览器扫描门禁；错误提示使用 assertive，成功提示使用 polite | 本地代码与浏览器门禁完成；需补充读屏器播报实测 |
| 可重复合成会话与全量回归 | `playwright.config.ts`、`tests/e2e/support/seed_api.py`、`admin_session.ts`、`web_session.ts` | 独立 Web/Admin 刷新会话；种子按 family 清理轮换链后重建；`check.ps1 -SkipInstall -IncludeE2E` | 本地统一门禁 28/28；真实 MySQL/Redis 并发、目标环境和生产验收待关闭 |
| WP3 第 9 轮回归 | `pnpm typecheck`、`pnpm lint`、Admin Vitest | 类型检查、ESLint、前端规范门禁、Admin 52/52、完整 28 项 Chromium 旅程通过 | 本地统一门禁通过；远端 CI `31307983187` 五个作业通过 |

## 2026-08-09 WP3 第 10 次迭代补充：剩余业务页面无障碍矩阵收口

| 需求 | 实现证据 | 自动化证据 | 状态与剩余风险 |
|---|---|---|---|
| Web 剩余业务页面响应式与无障碍 | `SubmissionsPage.vue`、`ReputationPage.vue`、`TrustCasesPage.vue`、`web-authenticated-accessibility.spec.ts` | 贡献、信誉、案件、活动页面的桌面/移动结构边界、无横向溢出、全页 PNG、Axe 严重/关键扫描 | 本地 Chromium 通过；真实移动设备、读屏器和跨浏览器待验收 |
| Admin 剩余业务页面响应式与无障碍 | `CandidateModerationPage.vue`、`TrustCasesPage.vue`、`SystemSettingsPage.vue`、`RiskAlertsPage.vue`、`admin-authenticated-accessibility.spec.ts` | 候选、案件、配置、告警页面的桌面/移动门禁；SelectTrigger 可辨识名称；候选页面超宽布局回归 | 本地 Chromium 通过；复杂写操作全键盘、读屏器和目标环境待验收 |
| Tailwind 语义样式与对比度 | 根 `tailwind.config.js` 绝对内容路径、Web/Admin 主题变量、共享 `--legacy-*` 变量 | Web/Admin 生产构建、工具类产物检查、Axe 实际对比度扫描 | 本地与 Linux CI 构建通过；跨平台字体与像素差异仍需独立批准 |
| 可诊断视觉门禁 | `tests/e2e/support/visual_assertions.ts` | 溢出元素前 10 项、Axe 目标/HTML/失败原因输出 | CI 失败定位能力完成；像素差异批准流程尚未自动化 |
| WP3 外部验收策略 | `visual-baseline-strategy.md`、`screen-reader-checklist.md`、`browser-matrix.md` | 明确 L1～L4 基线、NVDA/VoiceOver 清单和浏览器/设备矩阵 | 策略完成，实际 Edge/Firefox/Safari/读屏器/真实设备证据未产生 |
| WP3 第 10 轮回归 | `pnpm e2e`、`scripts/check.ps1 -SkipInstall -IncludeE2E` | 完整 30/30 Chromium 旅程、API/迁移/前端/Desktop/容器统一门禁 | 本地统一门禁与远端 CI `31310591798` 五个作业通过；目标环境和生产验收待关闭 |

## 2026-08-09 WP3 第 11 次迭代补充：Firefox 与 WebKit 跨引擎门禁

| 需求 | 实现证据 | 自动化证据 | 状态与剩余风险 |
|---|---|---|---|
| 三引擎隔离执行 | `playwright.config.ts`、根 `package.json` | Chromium/Firefox/WebKit 分别启动隔离服务与数据库，每个引擎 30 项 | 本地三引擎共 90/90；真实 Edge/Safari 和设备未验证 |
| 跨浏览器统一门禁 | `scripts/check.ps1 -IncludeCrossBrowserE2E` | API、迁移、前端、Desktop 与三引擎 E2E 在同一命令通过 | 本地完成；执行耗时增加但不使用无界重试 |
| GitHub Actions 浏览器矩阵 | `.github/workflows/ci.yml` | Chromium、Firefox、WebKit 独立安装、执行和失败制品命名 | 已通过，运行 `31319884808`（三个浏览器矩阵作业） |
| WebKit 键盘边界 | `tests/e2e/support/accessibility.ts` | Chromium/Firefox 首次 Tab；WebKit 直接聚焦并用 Enter 验证跳转 | WebKit 功能预检完成；真实 Safari 系统完整键盘访问与 VoiceOver 未验证 |
| 响应式跨引擎兼容 | 移动视口测试去除 Firefox 不支持的 `isMobile` 模拟 | 三引擎移动布局、无溢出和关键区域断言 | CSS 响应式预检完成；真实触摸/iOS/Android 未验证 |

## 2026-08-09 WP4 第 1 次迭代补充：安全审计与 SBOM 门禁

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| Python/Node 生产依赖审计 | `apps/api/pyproject.toml`、`pnpm-workspace.yaml`、`security-gate.ps1` | `pip-audit --strict`、`pnpm audit --prod --audit-level high` | 本地与 GitHub Actions 通过；当前阻断范围为 Python 已知漏洞及 Node 高危/严重漏洞 |
| API SAST | Bandit 1.9.4、`apps/api/src` | 中高置信度的中危/高危结果阻断；JSON 报告留存 | 首批门禁通过；前端 SAST、DAST 和人工测试未实施 |
| CycloneDX SBOM | API `pip-audit` SBOM、Anchore 仓库 SBOM | `verify_security_artifacts.py` 校验格式、版本和组件；`SHA256SUMS` 记录摘要 | 远端运行 `31322842317` 制品已下载并二次校验；尚未签名或形成来源证明 |
| 依赖风险修复 | `cryptography>=50,<51`、pytest `>=9.0.3`、pnpm `nanoid` override | API 全量测试、前端 lint/typecheck/test/build、安全审计 | 本地统一门禁和远端八个作业通过 |
| 安全证据制品 | `.github/workflows/ci.yml` | `security-evidence-<commit-sha>`，失败也上传已有报告，保留 30 天 | 首版完成；长期制品库、豁免治理和发布绑定待实现 |


## 2026-08-09 WP4 第 2 次迭代补充：镜像、Secret 与限期风险豁免门禁

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| 三个最终镜像高危/严重扫描 | `.github/workflows/ci.yml`、`infra/docker/*.Dockerfile` | Trivy `v0.73.0` JSON；API/Web/Admin 独立作用域 | 运行 `31331945963` 三个镜像均为 0；本机 Docker 引擎未运行，真实证据来自远端 Linux CI |
| 仓库 Secret 扫描 | Trivy filesystem secret scanner | `trivy-repository-secrets.json`、本地与远端扫描 | 结果 0；正式秘密托管与轮换仍待实施 |
| 默认阻断与限期接受 | `verify_release_security.py`、`security/risk-acceptances.json` | 5 项新增校验器测试；作用域/Finding/严重级别精确匹配；到期当天阻断 | 当前登记 0；正式组织审批系统未接入 |
| 双人批准 | 风险登记 `owner` 与 `approved_by` | 同人批准、重复登记、过期登记自动失败 | 静态治理完成，外部审批签字待实施 |
| 基础镜像风险整改 | Python 3.12.13 Alpine 3.23、Node 22.23.1 Alpine 3.23、Nginx 1.30.4 Alpine 3.24 | 首次运行 `31331415752` 阻断，更新后 `31331945963` 通过 | 未使用豁免掩盖首批风险 |
| 提交级证据 | `release-security-evidence-<commit-sha>`、`release-security-summary.json`、`RELEASE_SHA256SUMS` | 远端制品下载并由本地校验器二次复核 | finding/accepted/blocking/acceptance 均为 0；签名和长期证据库待实施 |
| 本地访问 | API、Web、Admin 开发进程 | 三个入口及两个前端 `/api` 代理健康检查 HTTP 200 | 本机可访问；不等同于 Compose 或预生产验收 |

## 2026-08-09 WP4 第 3 次迭代补充：API 动态安全与负向门禁

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| API 安全响应头 | `core/http_security.py` | 正常、401、405 响应测试；DAST `security_headers` | `nosniff`、禁止嵌入、最小 Referrer、受限 Permissions Policy、JSON CSP 和默认 `no-store` 已建立 |
| JSON 资源消耗上限 | `MAX_JSON_BODY_BYTES`、`HttpSecurityMiddleware` | 声明长度和分块请求均超过 1 MiB 时返回结构化 `413` | 首版完成；认证批量并发和长时压力仍待验证 |
| 匿名授权与 CORS | `test_wp4_dast_security.py`、`dast_security_gate.py` | 本人/隐私/管理资源 401；可信来源 200、非信任来源预检 400 | 匿名边界完成；两个已认证用户间 BOLA 尚未形成动态矩阵 |
| XSS 与凭据最小披露 | 动态合成标记 | 查询标记、密码和令牌不反射；方法错误无 traceback | API 响应基线完成；浏览器 DOM XSS、日志汇聚和人工测试未关闭 |
| 提交级 DAST 证据 | `dast-security` CI 作业 | 运行 `31340260242` 九作业通过；报告 8/8 | 首版完成；完整认证爬虫、ZAP/同类工具和预生产扫描待后续 |


## 2026-08-10 WP4 第 9 次迭代补充：Alertmanager 通知闭环与安全演练

| 需求 | 实现证据 | 自动化证据 | 当前状态与剩余风险 |
|---|---|---|---|
| Alertmanager 路由与恢复通知 | `infra/monitoring/alertmanager/alertmanager.yml`、Prometheus `alerting` 配置 | `amtool check-config`、Alertmanager firing/resolved 演练 | 工程路由完成；正式值班渠道认证、TLS、回执和升级策略待目标环境验收 |
| 重复通知抑制 | `group_by`、`group_interval`、`repeat_interval` | 两次相同 firing 仅交付一次的证据校验 | 合成单实例完成；跨 Alertmanager HA、静默和抑制矩阵待实施 |
| 通知敏感字段治理 | `scripts/alertmanager_receiver.py` 的字段白名单式脱敏 | 合成秘密标记未进入报告，`[REDACTED]` 存在，SHA-256 通过 | 仅证明内部证据持久化脱敏；第三方提供商传输/保留策略待签字 |
| 监控统一门禁 | `check.ps1 -IncludeMonitoring`、CI `monitoring` job | 配置、amtool、通知演练、证据校验和 Worker 积压均纳入门禁 | M5 工程准入增强；生产告警闭环尚未放行 |

当前估算：本地 MVP 约 99%，生产就绪约 75%。该估算不替代正式值班渠道、密钥轮换、多实例长时压测、预生产和业务/UAT 签字。


## 2026-08-10 WP4 第 8 次迭代补充：告警、仪表盘与队列积压演练

| 需求 | 实现证据 | 自动化证据 | 当前状态与剩余风险 |
|---|---|---|---|
| Prometheus 抓取与规则 | `infra/monitoring/prometheus/`、7 条低基数规则 | 静态校验器、官方 `promtool check config` | 配置和规则基线完成；Alertmanager 通知、值班确认和恢复演练待实施 |
| Grafana 最小仪表盘 | 固定 datasource UID、6 个面板和 provisioning | 监控 Compose smoke：Prometheus ready、target up、Grafana dashboard 自动加载 | 展示基线完成；生产认证、权限、持久化和多实例聚合待目标环境验收 |
| Worker 队列积压 | `observability.noop` 合成任务、`worker-backlog-drill.ps1` | 队列深度 `24 -> 0`，Worker ready，证据校验与 SHA-256 通过 | 单实例短时演练完成；长时混合负载、重试/失败容量和多 Worker 稳定性待实施 |
| 监控统一门禁 | `check.ps1 -IncludeMonitoring`、CI `monitoring` job | 配置、规则、演练和 artifact 上传均纳入门禁 | 当前为工程准入，不代表生产告警通知闭环 |

当前估算：本地 MVP 约 98%，生产就绪约 72%。该估算不替代 Alertmanager、长期混合压测、密钥轮换、预生产和业务/UAT 签字。

## 2026-08-10 WP4 第 7 次迭代补充：性能基线与可观测性出口

| 需求 | 实现证据 | 自动化证据 | 当前状态与剩余风险 |
|---|---|---|---|
| 精确查询 P95 | `performance-baseline.ps1`、`performance_probe.py` | 40 次正常负载查询，10.043 QPS，P95 96.998 ms，错误率 0% | 本地隔离 SQLite 基线满足 500 ms；MySQL/Redis/多实例混合压测待实施 |
| 短时 100 QPS | liveness 300 请求 | 99.808 QPS，P95 37.308 ms，错误率 0% | 建立代码级吞吐回归线，不代表业务容量 |
| Prometheus 指标 | `core/observability.py`、`GET /api/v1/metrics` | 六类指标、低基数路由、未匹配路径收敛和敏感值拒绝测试 | HTTP/DB/Redis/Worker/队列首版出口完成；抓取部署、仪表盘和告警待实施 |
| 请求关联与结构化日志 | `request_context.py`、`logging.py` | 合法请求号回显、JSON 完成日志、敏感字段脱敏 | 单 API 请求链路完成；跨 Worker/OpenTelemetry Trace 待实施 |
| 提交级性能证据 | `verify_performance_evidence.py`、CI `performance` 作业 | 固定结构、阈值、吞吐比例、最小披露和 SHA-256 校验 | 本地完成；远端运行结果在本轮提交后补充 |

当前估算：本地 MVP 约 98%，生产就绪约 70%。该估算不替代预生产、长期压测、告警通知、人工安全测试和业务/UAT 签字。


## 2026-08-11 WP4 第 28 次迭代补充：无外部 KMS 的生产秘密管理基线

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| 文件型应用秘密读取 | `apps/api/src/password_detective/core/config.py`、`*_FILE` 配置约定 | `apps/api/tests/test_file_backed_settings.py` 覆盖读取、冲突、缺失文件、大小上限和错误脱敏 | 已实现 |
| Docker Secrets 生产覆盖 | `docker-compose.production-secrets.yml`、`infra/docker/api-entrypoint.sh`、`infra/docker/api.Dockerfile` | 合同门禁验证无秘密值泄漏；本地 Docker MySQL/Redis/API 运行时烟测 ready，API 主进程降权且 inspect 无受管秘密值 | 本地验证完成，尚未切换目标服务器 |
| 独立秘密初始化和权限检查 | `scripts/manage_production_secrets.py init/verify` | 脚本测试验证拒绝覆盖、独立随机秘密、密钥环和连接地址一致性 | 已实现 |
| 认证加密备份和恢复 | `backup/restore` 子命令，Scrypt + Fernet | 明文不出现在备份、错误口令/篡改拒绝、恢复内容一致 | 已实现，目标服务器恢复演练待执行 |
| 候选秘密定期轮换 | `rotate-candidate` 先备份、再新增版本并保留旧密钥 | 轮换后当前版本变化、旧版本保留、轮换前备份可恢复 | 已实现；真实数据 dry-run/apply 待目标环境执行 |
| 外部 KMS 决策 | `项目文档/密码侦探社项目规格说明书-v3.0.md`、`docs/runbooks/production-secrets.md` | 文档与合同门禁固定当前生产基线 | 外部 KMS 非必选，未来按规模/审计重新评估 |
