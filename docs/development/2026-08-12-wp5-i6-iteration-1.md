# WP5-I6 第 1 个开发切片：可配置板块与群组治理

- 日期：2026-08-12
- 范围：动态板块目录、板块管理、社区群组、成员/角色治理、群组主题和私密内容可见性
- 结论：COMMUNITY-45～54 的本地代码、数据库迁移和自动化完成；目标 MySQL 与真实浏览器回归不在本切片本地验收范围内

## 1. 本轮实现

1. 新增 `community_boards`，将 `general`、`recovery_guides`、`verification`、`security` 迁移为确定性种子数据；主题保留 `board_code` 兼容字段，同时新增非空 `board_id` 外键。
2. 板块支持名称、说明、排序、最小发帖角色、正常/只读/停用状态；公开接口只返回可见目录，停用不物理删除历史内容。
3. Admin 新增 `/community/settings`，仅管理员且完成 TOTP 后可创建或修改板块；写操作继续要求 `Idempotency-Key`、客户端上下文和审计记录。
4. 新增公开、申请加入、私密三类群组，以及群组发现、群组主页、创建、更新、加入、退出、邀请、审批、拒绝、成员移除、角色调整和群主转移。
5. 群组角色固定为 `owner`、`moderator`、`member`；群主退出前必须完成受控转移，所有成员与治理变化均写入 `community_group_governance_events`。
6. 群组主题复用既有主题、评论、点赞、收藏、举报和内容治理链路；发布接口以 `group_slug` 选择群组，并要求当前有效成员资格。
7. Web 新增 `/community/groups`、`/community/groups/:groupSlug`，社区首页展示动态板块与群组摘要，发布页使用动态板块和群组目标；页面明确显示私密群组与角色权限说明。

## 2. 数据与安全边界

- Alembic `20260812_0032` 创建板块、群组、成员关系和治理事件表，并对既有主题完成板块外键回填；迁移提供降级路径。
- 板块创建和修改是管理员专属高风险操作，要求 TOTP；全站版主不能修改板块配置。
- 私密群组不向非成员出现在群组目录中，普通详情读取返回 404；其主题同时从列表、详情、公开主页、提及通知和群组筛选中隐藏。
- 全站管理员或版主不会仅因全站角色获得私密群组普通读取权；执行获授权的群组治理写入时，仅返回最小群组结果且不包含私密成员名单。
- 申请加入群组由群主或群组版主批准；私密群组只接受治理人员邀请。成员唯一约束和幂等写入避免重复成员关系。
- 群组停用和板块停用均使用逻辑状态，不级联删除主题；未来动态、搜索和通知必须复用本轮的可见性判断。

## 3. API 与前端路径

| 类型 | 项目 |
|---|---|
| 板块读取 | `GET /api/v1/community/boards` |
| 群组读取 | `GET /api/v1/community/groups`、`GET /api/v1/community/groups/{groupSlug}` |
| 群组治理 | `POST/PATCH /api/v1/community/groups`、`join`、`membership`、`members/{username}/decision`、`members/{username}/role` |
| 群组发帖 | `POST /api/v1/community/posts` 的 `group_slug`；`GET /api/v1/community/posts?group_slug=...` |
| 管理板块 | `GET/POST /api/v1/admin/community/boards`、`PATCH /api/v1/admin/community/boards/{boardCode}` |
| Web | `/community/groups`、`/community/groups/:groupSlug`、`/community/new` |
| Admin | `/community/settings` |

## 4. 自动化与验收边界

| 验收点 | 本地证据 |
|---|---|
| 固定板块种子与动态目录 | `test_board_catalog_is_seeded_and_configurable` |
| 管理员 MFA、版主拒绝和板块状态 | `test_community_board_admin.py` |
| 公开加入与群组发帖 | `test_public_group_join_is_idempotent_and_member_can_post` |
| 申请审批和私密邀请 | `test_approval_group_requires_owner_decision`、`test_private_group_owner_can_invite_member` |
| 私密内容不可旁路 | `test_private_group_never_leaks_to_non_members`、`test_private_group_filters_profiles_notifications_and_global_moderators` |
| 群主转移 | `test_owner_transfer_is_required_before_leave` |
| Web/Admin 页面渲染 | `CommunityGroupsPage.test.ts`、`CommunityGroupPage.test.ts`、`CommunityConfigurationPage.test.ts` |
| 数据库迁移 | Alembic `upgrade head -> downgrade 20260812_0031 -> upgrade head` |

本地统一门禁通过不替代目标 MySQL、部署后真实浏览器和生产权限配置验收。WP5-I7 必须在动态与通知读模型中复用本轮群组可见性，并补充点赞摘要、关注、群组申请/处理和角色变化通知。
