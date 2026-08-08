# WP2 第 4 次开发迭代：结果通知、SLA 自动升级与 Web 账号申诉

- 日期：2026-08-08
- 代码提交：`d193f21` 及后续第 4 轮提交
- 范围：案件结果通知 Outbox、失败重放、SLA 自动升级、Web 账号申诉表单和用户状态展示。

## 交付

- 新增 `trust_case_notifications`，处置事件自动生成去重通知；Worker 每 15 秒消费，失败最多 3 次并支持 Admin MFA 重放。
- 新增案件 `sla_due_at`、`escalated_at`、`escalation_count` 和 `last_escalation_reason`；Worker 每 60 秒将逾期 open/in_review 案件写入不可变升级事件，单案幂等一次。
- Admin 案件工作台改用原子处置接口，展示 SLA/升级和通知状态，失败通知可重新入队。
- Web `TrustCasesPage` 支持举报、贡献申诉和本人账号申诉，提交时服务端派生目标账号并展示 SLA 截止/升级状态。
- 新增 API、Web、Admin 的针对性测试和 SSR 渲染测试。

## 未关闭

本地 SQLite/内存通知门禁不等于正式 SMTP、Webhook、浏览器跨页面 E2E、真实 Worker/Redis、目标环境容量和生产放行。
