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

新增或改变跨模块约束时，应创建新 ADR，不直接改写已接受决策的历史结论。
