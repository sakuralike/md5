# 架构决策记录（ADR）

| 编号 | 决策 | 状态 |
|---|---|---|
| [ADR-0001](./0001-modular-monolith-and-monorepo.md) | 模块化单体与单仓结构 | 已接受 |
| [ADR-0002](./0002-candidate-secret-encryption.md) | 候选密码信封加密 | 已接受，KMS 提供商待定 |
| [ADR-0003](./0003-token-and-session-strategy.md) | 短期访问令牌与刷新令牌轮换 | 已接受 |
| [ADR-0004](./0004-desktop-verification-trust-boundary.md) | 桌面验证回执信任边界 | 已接受 |
| [ADR-0005](./0005-initial-archive-formats.md) | 首版压缩格式范围 | 临时接受，待产品确认 |
| [ADR-0006](./0006-distributed-request-protection.md) | 分布式限流与持久化幂等 | 已接受 |
| [ADR-0007](./0007-browser-session-boundary.md) | 浏览器会话与桌面令牌边界 | 已接受 |
| [ADR-0008](./0008-verification-evidence-state-and-points.md) | 验证证据、状态事件与积分结算边界 | 已接受 |
| [ADR-0009](./0009-backend-managed-desktop-update-channel.md) | 后端托管桌面更新通道与显式下载入口 | 已接受 |
| [ADR-0010](./0010-unified-trust-case-workflow.md) | 统一举报与申诉信任案件工作流 | 已接受 |
| [ADR-0011](./0011-points-projection-and-reputation-events.md) | 积分投影与不可变信誉事件 | 已接受 |
| [ADR-0012](./0012-reward-compensation-reconciliation.md) | 奖励补偿与状态驱动校正 | 已接受 |
| [ADR-0013](./0013-failure-surge-risk-alerts.md) | 短时间窗失败激增风险告警与隐私边界 | 已接受 |
| [ADR-0014](./0014-candidate-evidence-correlation-downweighting.md) | 候选内关联证据图与动态限权 | 已接受 |
| [ADR-0015](./0015-risk-alert-sla-assignment-notification-outbox.md) | 风险告警 SLA、值班指派与事务通知 Outbox | 已接受 |
| [ADR-0016](./0016-signed-webhook-and-notification-dead-letter-replay.md) | 签名 Webhook 与通知死信重放 | 已接受 |
| [ADR-0017](./0017-provider-neutral-smtp-email-delivery.md) | 提供商无关的 SMTP 邮件投递 | 已接受 |
| [ADR-0018](./0018-community-social-platform-boundaries.md) | 社区社交平台边界、事件一致性与私信安全 | 已接受，分阶段实施 |
| [ADR-0019](./0019-web-pending-pool-and-trusted-desktop-promotion.md) | Web 待验证池与可信桌面成功直入 | 已接受 |
| [ADR-0020](./0020-plugin-process-isolation-model.md) | 插件进程隔离模型与唯一通路 | 已接受 |
| [ADR-0021](./0021-appcontainer-jobobject-boundary.md) | AppContainer、Job Object 与显式 OS 隔离边界 | 已接受 |
| [ADR-0022](./0022-parameterized-capability-model.md) | 参数化能力模型与 Tier 授权 | 已接受，分阶段实施 |
| [ADR-0023](./0023-plugin-signing-and-revocation.md) | 插件平台签章、OpenBao Transit 与撤销策略 | 已接受 |
| [ADR-0024](./0024-host-self-protection.md) | 宿主自我降权与双进程边界 | 已接受，P2 实施 |


新增或改变跨模块约束时，应创建新 ADR，不直接改写已接受决策的历史结论。
