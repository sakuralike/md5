# 社区回复数投影运行手册

## 1. 适用范围

本手册用于审计和修复 `community_posts.reply_count` 与公开回复事实之间的不一致。公开回复的唯一统计口径为：

- 评论状态为 `published`；
- `deleted_by_author_at` 为空；
- 作者删除占位和管理员治理移除内容均不计入公开回复数。

工具不会修改评论状态、内容、作者关系、主题状态或时间字段。报告仅包含主题 ID、已存计数和期望计数，不输出评论正文、账号、邮箱、IP、令牌或秘密。

## 2. 变更窗口前置检查

1. 确认当前部署代码已经包含作者删除和治理移除的在线写入修复，否则重建后仍可能再次产生偏差。
2. 确认数据库备份可以恢复，并记录备份标识和恢复验证结果。
3. 暂停会批量创建、删除或治理社区回复的作业；正常低流量写入可通过短变更窗口控制。
4. 使用与 API 相同的 `DATABASE_URL` 或 `DATABASE_URL_FILE`，不得在命令行明文记录生产凭据。

## 3. 默认 dry-run 审计

在仓库根目录执行：

```powershell
apps/api/.venv/Scripts/python.exe scripts/rebuild_community_reply_counts.py `
  --report .local/community-reply-count/dry-run.json
```

预期输出：

- `status` 为 `dry-run`；
- `scanned_posts` 为扫描的主题总数；
- `inconsistent_posts` 为存在偏差的主题数；
- `updated_posts` 必须为 `0`；
- `changes` 只列出主题 ID、已存计数和期望计数。

若异常数量超出预期，先停止 apply，核对数据库目标、部署版本、评论状态和备份，不得直接修改报告后继续。

## 4. 应用修复

在已批准的变更窗口执行：

```powershell
apps/api/.venv/Scripts/python.exe scripts/rebuild_community_reply_counts.py `
  --apply `
  --report .local/community-reply-count/apply.json
```

`--apply` 在单个数据库事务中更新所有不一致主题。命令失败或进程在提交前中断时，事务应回滚；不得通过手工跳过异常记录来伪造完成状态。

## 5. 修复后复核

再次执行 dry-run：

```powershell
apps/api/.venv/Scripts/python.exe scripts/rebuild_community_reply_counts.py `
  --report .local/community-reply-count/verify.json
```

验收条件：

1. `inconsistent_posts = 0`；
2. `updated_posts = 0`；
3. 随机抽查至少一个无回复主题、一个公开回复主题、一个作者删除占位主题和一个治理移除回复主题；
4. 社区首页与主题详情显示的公开回复数一致；
5. 目标环境日志无数据库错误或响应异常。

## 6. 回滚

该工具只重算可重建投影。若 apply 后发现统计口径或部署版本错误：

1. 立即停止社区相关发布和治理写入；
2. 恢复变更前数据库备份，或在确认正确统计口径后再次运行修复工具；
3. 对恢复后的数据库重新执行 dry-run；
4. 记录偏差原因、影响主题数量和最终复核报告。

不得把旧计数报告当作数据库恢复文件，也不得为恢复计数而还原评论正文或删除状态。

## 7. 本地合同测试

```powershell
apps/api/.venv/Scripts/python.exe -m ruff check `
  scripts/rebuild_community_reply_counts.py `
  scripts/tests/test_rebuild_community_reply_counts.py

apps/api/.venv/Scripts/python.exe -m pytest `
  scripts/tests/test_rebuild_community_reply_counts.py

./scripts/check.ps1 -SkipInstall
```
