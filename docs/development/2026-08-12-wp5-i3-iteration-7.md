# WP5-I3 第 7 个开发切片：社区提及通知闭环

- 日期：2026-08-12
- 范围：主题/回复 `@用户名` 提及、站内通知列表、未读计数、单条/全部已读和 Web 通知中心
- 结论：本地编码与专项自动化完成；本轮提交后的目标环境部署作为后续发布动作单独验证

## 1. 本轮实现

1. 新增 `community_notifications`，以接收人、通知类型、来源类型和来源 ID 组成业务唯一键，防止幂等重放、重复提及或内容编辑造成重复投递。
2. 主题标题/正文、回复正文发布或编辑时解析 `@用户名`；用户名按不区分大小写去重，每次内容最多处理 10 个提及，忽略不存在、非活动和作者本人账号。
3. 通知只保存最多 180 字的纯文本最小化摘要、来源标识和行为人，不复制完整主题或回复正文。
4. 新增本人通知游标列表、未读总数、单条已读和全部已读 API；已读写入要求 `Idempotency-Key`，并以接收人重新校验资源归属。
5. 新增 Web `/community/notifications` 通知中心、主导航入口、加载更多、刷新、单条/全部已读和主题回链。

## 2. 安全和一致性边界

- 通知和社区内容在同一数据库事务内写入；通知写入失败时不提交内容变更。
- 业务唯一约束是最终去重边界，服务层同时在写入前排除已有投递。
- 通知列表、已读和批量已读只允许接收人访问；对他人的通知 ID 返回统一不存在错误。
- 本切片尚未实现社交屏蔽/提及偏好；这些能力仍按 COMMUNITY-43、COMMUNITY-68、COMMUNITY-73、COMMUNITY-76 在后续迭代接入。
- 本切片不提供邮件摘要、SSE 或外部推送，数据库通知是事实来源。

## 3. API

```text
GET  /api/v1/community/notifications?cursor=...&limit=20&unread_only=false
POST /api/v1/community/notifications/{notification_id}/read
POST /api/v1/community/notifications/read-all
```

列表响应同时返回 `unread_count`，因此首版不额外增加独立未读计数请求。

## 4. 自动化验收

| 验收项 | 自动化证据 | 状态 |
|---|---|---|
| 发布主题提及去重、自提及/未知用户过滤 | `test_mentions_create_deduplicated_recipient_notifications` | 已通过 |
| 回复提及、游标分页和批量已读 | `test_comment_mentions_and_read_all_are_scoped_to_recipient` | 已通过 |
| 越权读取/已读阻断 | 同上，非接收人写入返回 404 | 已通过 |
| Web 通知中心基础渲染 | `CommunityNotificationsPage.test.ts` | 已通过 |
| Web 认证、路径编码和幂等请求头 | `services/community.test.ts` | 已通过 |
| Alembic 升级/降级往返与全仓回归 | `scripts/check.ps1 -SkipInstall` | 提交前执行 |

## 5. 后续

WP5-I3 的业务编码项已收口。下一轮进入 WP5-I4 内容互动，优先实现主题/回复点赞、主题收藏、唯一约束、计数投影和本人收藏列表；当前通知模型后续可扩展点赞摘要，但本轮不提前计入完成度。
