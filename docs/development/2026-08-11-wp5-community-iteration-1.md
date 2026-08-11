# 2026-08-11 WP5 第 1 次迭代：社区论坛首轮迁移

## 目标

参考 Zibll 主题的社区/论坛信息架构，将“分区—主题—回复—锁定”的可复用产品模式重构到密码侦探社现有 FastAPI、Vue 3、Shadcn-Vue 和 Tailwind 架构中。

## Zibll 功能分析

已检查 `E:/只比主题/zibll/inc/functions/bbs`、`message`、用户等级/权限及相关页面。可迁移的产品模式包括：

- 论坛首页与分区/版块导航；
- 主题列表、主题详情、回复/评论；
- 置顶、锁定、热度与基础版主管理；
- 用户身份、通知、私信、关注、点赞、收藏和标签等扩展能力。

本轮只选择前四项中最小可用的分区、主题、回复和锁定数据模型；不直接复制 Zibll 的专有代码、样式、模板或脚本。

## 已实现

- 四个固定分区：社区广场、恢复指南、验证协作、安全与隐私。
- 公开 `GET /api/v1/community/boards`、`/posts`、`/posts/{post_id}`。
- 已验证邮箱账号创建主题、回复；规则确认由后端强制。
- 纯文本内容校验与前端文本插值，限制正文长度并移除 NUL。
- 主题回复计数、最近活动时间、置顶/锁定字段和锁定拒绝回复。
- 写接口限流和 `Idempotency-Key`，重复请求返回原业务结果。
- Web `/community` 页面、分区筛选、主题详情、回复展示和发帖表单。

## 验证记录

- `apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_community.py -q`：4 passed。
- `pnpm --filter @password-detective/web typecheck`：通过。
- `pnpm --filter @password-detective/web lint`：通过。
- `pnpm --filter @password-detective/web test -- --run`：12 个测试文件、25 个测试通过。
- 社区模块 Ruff 检查：通过。

## 后续任务

1. Admin 版主队列：举报、移除、恢复、锁定和审计。
2. 社区通知：主题回复、提及和案件结果通知，接入既有 Outbox/SMTP/Webhook。
3. 社交扩展：关注分区/用户、收藏、点赞、标签和主题搜索；先完成隐私与限流设计。
4. 目标服务器执行 Alembic 迁移并完成浏览器真实路径回归。
