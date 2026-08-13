# 哈希值详情页开发切片

日期：2026-08-13

## 本轮目标

为每个合法哈希值提供可访问的详情页，集中展示哈希算法、摘要、公开档案候选和社区互动。详情页不展示明文密码、令牌或其他敏感凭据。

## 已实现

- Web 路由：`/hash/:algorithm/:digest`。
- 首页精确查询结果新增“查看哈希详情”，未匹配哈希也可以打开详情页。
- API：`GET /api/v1/hashes/{algorithm}/{digest}`。
- 哈希点赞：`PUT/DELETE /api/v1/hashes/{algorithm}/{digest}/like`。
- 哈希评价投票：`PUT /api/v1/hashes/{algorithm}/{digest}/vote`，选项为 `useful`、`not_useful`，同一用户可修改自己的投票。
- 哈希评论：`POST /api/v1/hashes/{algorithm}/{digest}/comments`，支持父评论和社区规则确认。
- 评论点赞：`PUT/DELETE /api/v1/hashes/{algorithm}/{digest}/comments/{comment_id}/like`。
- 所有登录写操作使用认证、限流、`Idempotency-Key` 和唯一约束；哈希与评论输入沿用算法/长度/内容校验。
- 新增 Alembic 迁移 `20260813_0034_hash_detail.py`，建立哈希点赞、投票、评论和评论点赞表。

## 设计边界

- “有帮助/需核实”是针对哈希详情的社区评价，不等同于候选密码的成功/失败证据；候选证据仍通过现有 `/candidates/{candidate_id}/feedback` 维护。
- 公开详情沿用档案查询的脱敏候选策略，未登录用户只读取公开元数据；未匹配哈希返回空互动集合，不自动创建档案记录。
- 当前评论列表先返回最近 100 条，下一轮可补充分页、编辑/删除、举报和通知联动。
- 当前评论点赞 API 已完成，页面已提供入口；下一轮补充评论回复、分页和举报闭环。

## 验证

- API：`apps/api/tests/test_m2_archive_core.py` 新增详情、点赞、投票、评论、评论点赞和未匹配哈希测试。
- Web：新增 `apps/web/src/pages/HashDetailPage.test.ts`。
- 门禁：API 归档核心测试通过；Web typecheck、lint、Vitest 通过。

## 后续

1. 在目标服务器执行迁移并回归真实 MySQL。
2. 增加评论分页、回复、编辑/删除、举报和社区通知。
3. 增加详情页视觉回归和搜索结果到详情页的浏览器旅程。
