# WP5-I4 第 1 个开发切片：社区点赞与收藏闭环

- 日期：2026-08-12
- 范围：主题点赞、回复点赞、主题收藏、本人收藏列表、计数投影和失效引用清理
- 结论：COMMUNITY-32～35 的本地编码与自动化完成；COMMUNITY-36 点赞摘要通知留待 WP5-I7 统一通知聚合

## 1. 本轮实现

1. 新增主题点赞、回复点赞和主题收藏三张事实关系表，并以数据库唯一约束保证同一用户对同一目标最多一条有效关系。
2. 为主题和回复新增 `like_count` 投影；每次互动写入后从关系表重新计数，避免幂等重放或重复请求造成累计漂移。
3. 新增主题/回复点赞与取消点赞、主题收藏与取消收藏 API。所有写操作要求登录、端点限流和 `Idempotency-Key`。
4. 主题详情与回复列表在可选登录态下返回当前用户的点赞/收藏状态；匿名读取只返回公开计数，不暴露用户关系。
5. 新增仅本人可见的游标收藏列表和 Web `/community/bookmarks` 页面，支持加载更多、取消收藏以及清理已移除或无权访问的失效引用。
6. 主题详情页新增可撤销点赞、收藏按钮和回复点赞按钮；未登录用户触发互动时进入登录提示，不把前端状态作为授权依据。

## 2. 数据和安全边界

- `community_post_likes` 唯一 `(user_id, post_id)`；`community_comment_likes` 唯一 `(user_id, comment_id)`；`community_post_bookmarks` 唯一 `(user_id, post_id)`。
- 已移除或不可访问的主题/回复拒绝新增点赞或收藏，但允许关系所有者取消互动，避免产生无法清理的私有引用。
- 收藏列表不返回收藏者名单，也不向作者披露谁收藏了主题；仅登录用户可读取自己的收藏记录。
- 收藏来源失效时返回 `post = null`，不通过收藏列表旁路泄露标题、正文或作者资料。
- 点赞计数是可重建投影，事实关系表是最终事实来源。本切片不发送每次点赞即时通知。
- 旧幂等记录若缺少本轮新增展示字段，由响应模型默认值兼容，避免历史重放因模式扩展失败。

## 3. API

```text
PUT    /api/v1/community/posts/{post_id}/like
DELETE /api/v1/community/posts/{post_id}/like
PUT    /api/v1/community/comments/{comment_id}/like
DELETE /api/v1/community/comments/{comment_id}/like
PUT    /api/v1/community/posts/{post_id}/bookmark
DELETE /api/v1/community/posts/{post_id}/bookmark
GET    /api/v1/community/bookmarks?cursor=...&limit=20
```

主题详情与回复列表支持可选 Bearer 登录态，以返回 `viewer_has_liked` 和 `viewer_has_bookmarked`；无登录态时这些字段为 `false`。

## 4. 自动化验收

| 验收项 | 自动化证据 | 状态 |
|---|---|---|
| 主题/回复点赞幂等、唯一计数和取消关系 | `test_post_and_comment_likes_are_idempotent_and_project_counts` | 已通过 |
| 匿名与本人互动状态隔离 | 同上，分别断言匿名和认证读取 | 已通过 |
| 收藏仅本人可见、游标分页和失效引用清理 | `test_bookmarks_are_private_paginated_and_removed_targets_are_cleanup_only` | 已通过 |
| 已移除内容禁止新增互动 | 上述后端测试的负向分支 | 已通过 |
| Web 主题详情与收藏页基础渲染 | `CommunityPostPage.test.ts`、`CommunityBookmarksPage.test.ts` | 已通过 |
| Web 认证、路径编码、方法和幂等请求头 | `services/community.test.ts` | 已通过 |
| Alembic 升级/降级往返与全仓回归 | `scripts/check.ps1 -SkipInstall` | 提交前执行 |

## 5. 后续

下一轮进入 WP5-I5 公开主页和关系图，优先实现用户关注/粉丝、公开资料、隐私偏好、屏蔽和静音。COMMUNITY-36 点赞摘要通知在 WP5-I7 与事件 Outbox、通知偏好和聚合去重一起实现，避免本轮形成第二套临时通知模型。
