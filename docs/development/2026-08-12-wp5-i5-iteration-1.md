# WP5-I5 第 1 个开发切片：社区公开主页与关系图谱

- 日期：2026-08-12
- 范围：公开资料、关注/粉丝、隐私策略、屏蔽、静音、用户名不可变与社区资料设置
- 结论：COMMUNITY-37～44 的本地代码、数据库迁移与自动化完成；目标 MySQL、真实浏览器回归和私信交付不在本切片验收范围内

## 1. 本轮实现

1. 新增 `community_public_profiles`、`community_user_follows`、`community_user_blocks`、`community_user_mutes`，并通过 Alembic `20260812_0031` 管理前滚、降级和重新前滚。
2. 提供公开主页、粉丝/关注列表、本人资料、本人隐私偏好以及关注、屏蔽、静音的可撤销 API。
3. 关注事实表使用唯一约束；粉丝数和关注数在每次关系变更后从事实表重建，避免重复请求造成累计漂移。
4. 公开资料只投影用户名、显示名、合成头像、角色、等级、公开简介、注册月份、公开统计和允许公开的主题/评论；不返回邮箱、登录状态、精确注册时间、IP、设备、积分明细、私密群组或隐私策略。
5. 屏蔽会删除双方既有关注关系，拒绝后续关注，并在公开资料、主题、回复、收藏和提及处理中隐藏双方；静音仅影响操作者自己的读取视图，不通知对方且不删除关注关系。
6. Web 新增 `/community/users/:username`、`/community/users/:username/followers`、`/community/users/:username/following` 和 `/community/settings`，并将主题、回复、收藏作者链接到公开主页。
7. 账户用户名在注册后不可修改；公开显示名在社区资料页维护，服务端去除 NUL 和首尾空白后执行非空与长度校验。

## 2. 数据与安全边界

- 关注、屏蔽、静音均以当前有效用户为目标；禁止对自身操作，禁用账户不进入公开主页或关系列表。
- 关系写操作要求登录、端点限流、`Idempotency-Key`、客户端上下文和最小化审计。
- 粉丝/关注列表遵循资料所有者的公开性设置；所有者本人可读取自己的私有列表，旁观者收到拒绝，不通过计数或游标泄露关系对象。
- `message_policy` 已持久化为未来私信的授权输入，但本轮不声明私信已实现；WP5-I9 必须同时复用消息策略与屏蔽限制。
- 提及逻辑已接入屏蔽和 `mention_policy`；屏蔽关系及静音关系都不会被社区读取接口旁路暴露。

## 3. API 与前端路径

| 类型 | 项目 |
|---|---|
| 资料 | `GET/PATCH /api/v1/community/me/profile`、`GET /api/v1/community/users/{username}` |
| 隐私 | `PATCH /api/v1/community/me/privacy` |
| 关系列表 | `GET /api/v1/community/users/{username}/followers`、`GET /api/v1/community/users/{username}/following` |
| 关系写入 | `PUT/DELETE /api/v1/community/users/{username}/follow`、`block`、`mute` |
| Web | `/community/users/:username`、`/community/users/:username/followers`、`/community/users/:username/following`、`/community/settings` |

## 4. 自动化与验收边界

| 验收点 | 本地证据 |
|---|---|
| 最小化公开资料和隐私更新 | `test_public_profile_update_privacy_and_safe_projection` |
| 关注唯一性、禁止自关注、私有列表 | `test_follow_relationships_are_unique_and_private_lists_stay_private` |
| 屏蔽解除关注和阻断后续关系 | `test_block_removes_follow_edges_and_prevents_follow` |
| 静音不改变关注、读取过滤 | `test_block_and_mute_filter_existing_posts_from_read_paths` |
| 用户名不可变 | `test_username_cannot_change_after_registration` |
| Web 页面渲染 | `CommunityProfilePage.test.ts`、`CommunityRelationsPage.test.ts`、`CommunitySettingsPage.test.ts` |

目标 MySQL 迁移、目标浏览器与未来私信通道仍需在部署和 WP5-I9 中分别验证；本地门禁通过不替代生产验收。
