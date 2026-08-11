# WP4 Staging 自动发布决策记录模板

> 本模板只允许填写合成或脱敏信息。不得粘贴密码、令牌、连接串、私钥、Cookie、真实用户数据或个人信息。

## 1. 变更信息

| 字段 | 值 |
|---|---|
| 环境 | staging |
| 变更编号 | `<CHANGE-ID>` |
| 候选版本/提交 | `<COMMIT-SHA>` |
| 候选文件树 | `<TREE-SHA>` |
| 验证开始时间 | `<UTC-TIMESTAMP>` |
| 验证结束时间 | `<UTC-TIMESTAMP>` |
| 数据范围 | 仅合成数据 |
| 当前决策 | `PENDING` |

## 2. 必需证据

| 证据 | 文件或链接 | 校验结果 | 备注 |
|---|---|---|---|
| 准入计划 | `staging-readiness-plan.json` | `<PASS/FAIL>` | 配置合同和容量预算 |
| 长时混合稳定性 | `multi-instance-stability-report.json` | `<PASS/FAIL>` | 不少于 4 小时 |
| 资源趋势 | `resource-trend-report.json` | `<PASS/FAIL>` | CPU、内存、连接数和队列 |
| MySQL 高可用切换 | `mysql-ha-failover-report.json` | `<PASS/FAIL>` | RTO/RPO 与数据一致性 |
| Redis 高可用切换 | `redis-ha-failover-report.json` | `<PASS/FAIL>` | readiness、限流和任务队列恢复 |
| 完整性校验 | `checksums.sha256` | `<PASS/FAIL>` | 所有证据文件 |
| 安全门禁 | `<CI-RUN-OR-EVIDENCE>` | `<PASS/FAIL>` | SAST、依赖、DAST、镜像和秘密扫描 |
| 候选密钥轮换 | `<ROTATION-EVIDENCE>` | `<PASS/FAIL>` | 正向轮换与回滚 |

## 3. 容量预算

| 项目 | 计划值 | 实测峰值 | 结论 |
|---|---:|---:|---|
| 数据库客户端进程 | `<COUNT>` | `<COUNT>` | `<PASS/FAIL>` |
| 单进程最大连接数 | `<COUNT>` | `<COUNT>` | `<PASS/FAIL>` |
| 计划最大连接数 | `<COUNT>` | `<COUNT>` | `<PASS/FAIL>` |
| 允许连接数预算 | `<COUNT>` | `<COUNT>` | `<PASS/FAIL>` |
| 剩余安全余量 | `<COUNT>` | `<COUNT>` | `<PASS/FAIL>` |

## 4. 长时稳定性结论

- 执行时长：`<SECONDS>`
- API / MySQL / Redis / Celery 操作数：`<COUNTS>`
- 错误率：`<PERCENT>`
- 最大连续错误数：`<COUNT>`
- P95：`<VALUES>`
- 单 Worker 故障期间服务状态：`<PASS/FAIL>`
- 最终队列深度：`<COUNT>`
- 最终 readiness：`<HTTP-STATUS>`
- 资源水位是否全部低于阈值：`<YES/NO>`

## 5. 高可用切换结论

### MySQL

- 切换方式：`<MODE>`
- 实测 RTO：`<SECONDS>`
- 实测 RPO：`<SECONDS>`
- 写入、读取和数据一致性：`<PASS/FAIL>`
- 回切结果：`<PASS/FAIL>`

### Redis

- 切换方式：`<MODE>`
- 实测 RTO：`<SECONDS>`
- 实测 RPO：`<SECONDS>`
- readiness、限流和 Celery 恢复：`<PASS/FAIL>`
- 回切结果：`<PASS/FAIL>`

## 6. 未关闭风险与回滚

| 风险 | 严重度 | 负责人角色 | 截止条件 | 是否阻断 |
|---|---|---|---|---|
| `<RISK>` | `<P0-P3>` | `<ROLE>` | `<EXIT-CRITERIA>` | `<YES/NO>` |

- 回滚版本：`<ROLLBACK-COMMIT>`
- 回滚步骤：`<RUNBOOK-SECTION>`
- 回滚触发条件：`<TRIGGERS>`
- 回滚验证：`<CHECKS>`

## 7. 强制决策规则

出现以下任一情况必须判定为 `NO-GO`：

1. 任一必需证据缺失、校验失败或 SHA-256 不匹配；
2. 长时窗口少于 4 小时，或使用了非合成数据；
3. 连接池计划超过版本化容量预算，或实测连接数侵占保留连接；
4. MySQL/Redis 高可用切换未完成，或 RTO/RPO 超过 profile 阈值；
5. 错误率、连续错误、P95、资源水位或队列深度超过阈值；
6. 存在未接受的 P0/P1 风险、未验证回滚或生产秘密管理未关闭；
7. 发布候选提交、证据归档或校验和缺失，或自动证据门禁未输出 `go`。

## 8. 自动决策

- 决策模式：`automated-evidence-gate`
- 候选提交：`<COMMIT-SHA>`
- 证据归档 SHA-256：`<ARCHIVE-SHA256>`
- 自动校验结果：`<GO/NO-GO>`
- 决策时间：`<UTC-TIMESTAMP>`
- 决策说明：`<SUMMARY>`

本项目不要求人员签字。只有所有必需证据、校验和、风险阈值和回滚检查均通过时，自动门禁才能输出 `GO`；任何缺失或失败均为 `NO-GO`。
