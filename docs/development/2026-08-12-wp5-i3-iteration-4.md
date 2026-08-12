# WP5-I3 第 4 个开发切片：回复数投影一致性收口

- 日期：2026-08-12
- 范围：公开回复数在线写入一致性、离线审计/重建、统一门禁
- 非范围：移动端 Playwright 主旅程、真实目标环境执行、提及通知、点赞/收藏

## 实现

1. 作者删除回复时，在同一事务内将主题 `reply_count` 减一并保持下限为 0。
2. 对已经存在 `deleted_by_author_at` 的回复拒绝再次删除，返回 `community.comment_already_deleted`，避免通过不同幂等键重复推进版本或重复扣减。
3. 管理员移除作者已删除的占位回复时不再二次扣减；仅仍公开且未被作者删除的回复参与扣减。
4. 新增 `community.projection.rebuild_reply_count_projection`，按评论事实计算每个主题的期望公开回复数。
5. 新增 `scripts/rebuild_community_reply_counts.py`：默认 dry-run，显式 `--apply` 才写入，可输出脱敏 JSON 报告。
6. 将重建脚本 Ruff 和 pytest 纳入 `scripts/check.ps1` 默认统一门禁。

## 安全与数据边界

- 投影口径只读取评论状态、作者删除时间和主题 ID，不读取或输出评论正文。
- 报告不包含用户名、邮箱、IP、令牌、秘密或个人资料。
- 写入只更新 `community_posts.reply_count`，不更改主题/评论状态和内容。
- 生产执行必须先 dry-run、确认备份可恢复，再在变更窗口使用 `--apply`。

## 自动化覆盖

- 作者删除回复后公开回复数从 1 变为 0。
- 使用新幂等键重复删除返回 409，公开回复数保持 0。
- 作者删除占位被治理移除时不重复扣减。
- dry-run 识别异常但不写入。
- apply 只更新异常主题，并排除作者删除与治理移除评论。

## 结论

COMMUNITY-31 的本地编码和自动化已完成。WP5-I3 尚余移动端 Playwright、真实目标环境回归和提及通知，不能据此声明整个迭代完成。

## 验证结果

- 社区与投影专项：`apps/api/tests/test_community.py` 加离线投影测试共 14 项通过。
- 统一门禁：`pwsh ./scripts/check.ps1 -SkipInstall` 通过，覆盖后端 Ruff/pytest/覆盖率、Alembic 前滚-降级-前滚、回复数脚本 Ruff/pytest、前端 lint/typecheck/Vitest/build。
- 本轮未执行真实目标 MySQL、移动端 Playwright 和服务器部署，因此这些证据继续标记为未完成。
