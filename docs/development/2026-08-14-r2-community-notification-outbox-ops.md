# R2 Admin 社区通知 Outbox 运维开发记录

- 日期：2026-08-14
- 范围：网页管理端与 API；Windows 桌面端 UI 尚未冻结，本轮不新增桌面功能。
- 对应计划：WP5-I7 通知可靠性第三轮。

## 1. 本轮目标

关闭社区通知链路缺少运维入口的风险，使管理员可以查看积压与失败原因，并在不绕过通知偏好、屏蔽关系和内容可见性规则的前提下安全重放单条失败事件。

## 2. API 与数据模型

- 迁移：`20260814_0036_community_notification_outbox_ops`。
- Outbox 新增：`replay_count`、`last_replayed_at`、`last_replayed_by_id`。
- 指标：`GET /api/v1/admin/community/notification-outbox/metrics`。
- 列表：`GET /api/v1/admin/community/notification-outbox`，支持 `status`、`kind`、`error_code`、`page`、`page_size`。
- 重放：`POST /api/v1/admin/community/notification-outbox/{event_id}/replay`。

列表不返回通知正文、邮箱、令牌或秘密材料，仅展示事件 ID、用户名、通知类型、投递状态、尝试次数、时间、错误码和重放元数据。

## 3. 安全与一致性

1. 指标、列表和重放均仅允许已完成 TOTP 的管理员，审核员无权访问。
2. 重放仅接受 `failed` 事件，并在数据库行锁内再次验证状态。
3. 管理员必须使用当前密码和 TOTP 申请用途为 `admin_community_notification_ops` 的短时一次性凭据。
4. 重放请求要求原因、`Idempotency-Key` 和速率限制，并写入 `community.notification_outbox.replay` 审计记录。
5. API 只把事件重置为 `pending`；Worker 随后重新检查通知偏好、双方屏蔽和内容可见性，不允许管理端直接强制投递。

## 4. Admin 页面

新增 `/community/notifications`“社区通知 Outbox 工作台”：

- 展示待投递、失败、24 小时失败、已到期待处理和最老积压指标。
- 按状态、通知类型、错误码筛选，最多展示 50 条。
- 展示尝试次数、错误码、失败时间和历史重放次数。
- 单条重放表单要求原因、当前密码和 TOTP，并明确一次性凭据及 Worker 二次校验边界。
- 重放幂等键复用管理端共享 `createClientId()`：HTTPS 优先使用 `crypto.randomUUID()`，HTTP 目标环境回退到 `crypto.getRandomValues()`，避免非安全上下文无法提交。

## 5. 自动化与目标环境验收

本轮本地验收包括 API 定向测试、Ruff、Admin typecheck/lint/test/build、迁移前滚/回滚和统一门禁。Staging 验收需使用合成通知事件完成：

1. 人工构造一条 `failed` 社区通知 Outbox 事件。
2. 管理员从 `/community/notifications` 查询到错误码与尝试次数。
3. 输入原因、当前密码和 TOTP 完成一次性再认证及重放。
4. 页面刷新后事件从失败队列消失，数据库记录 `replay_count=1` 和重放操作者。
5. Worker 将事件处理为 `delivered`，审计日志存在且不含密码、TOTP 或再认证令牌。

## 6. 后续范围

- 邮件摘要真实投递、退信/送达证据与目标 SMTP 验收。
- Redis Pub/Sub 或等价广播机制，降低多 API 实例下 SSE 数据库轮询压力。
- 多标签页已读状态同步、SSE 连接指标和长连接容量验证。
