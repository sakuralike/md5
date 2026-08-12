# WP5-I3 第 6 个开发切片：MySQL 迁移与目标服务器部署收口

- 日期：2026-08-12
- 范围：COMMUNITY-14～31 的目标 MySQL 迁移兼容性、失败重入和部署验证
- 结论：编码与真实 MySQL 修复验证完成；最终版本部署以本轮提交后的服务器验收记录为准

## 1. 问题背景

目标服务器执行 Alembic `20260812_0028` 时，MySQL 8.4 返回错误 1093：迁移在更新
`community_comments` 的同时，通过标量子查询再次读取同一目标表。由于 MySQL DDL 为非事务执行，
失败发生前新增字段、索引和外键已经生效，但 Alembic 版本仍停留在 `20260811_0027`。

## 2. 本轮实现

1. MySQL 数据回填改为自连接 `UPDATE ... INNER JOIN ...`，避免目标表子查询限制。
2. `20260812_0028` 在升级前反射现有表、字段、索引和外键；已存在对象不重复创建。
3. 保留 SQLite 等非 MySQL 方言的相关子查询更新，维持本地迁移门禁兼容。
4. 新增迁移专项测试，覆盖 MySQL SQL 形态和“DDL 已完成但版本号未推进”的重试场景。

## 3. 安全与恢复边界

- 部署前保留当前代码目录回滚副本和带 SHA-256 的发布包。
- 迁移失败时不滚动替换应用容器，原服务继续健康运行。
- 修复迁移只补齐未完成的数据回填并推进 Alembic 版本，不删除已存在业务数据。
- 服务器连接凭据、应用秘密和数据库口令不写入仓库、测试报告或日志文档。

## 4. 验收项

| 验收项 | 证据 | 状态 |
|---|---|---|
| MySQL 1093 规避 | `test_mysql_backfill_uses_join_update` | 已通过 |
| 非事务 DDL 失败重入 | `test_mysql_retry_after_non_transactional_ddl_only_runs_backfill` | 已通过 |
| 社区 API 回归 | `apps/api/tests/test_community.py` | 已通过 |
| 本地全量质量门禁 | `pwsh ./scripts/check.ps1 -SkipInstall` | 提交前执行 |
| 目标 MySQL 迁移到 head | Alembic `current`、字段/索引/外键检查 | 已完成：版本为 `20260812_0028 (head)` |
| 目标服务与社区页面 | live/ready、社区首页 API、Web/Admin HTTP 检查 | 已完成：健康检查和公开社区/Web/Admin HTTP 检查均返回 200 |

## 5. 目标环境部署复核

- 已部署提交：`8e0066f`（`fix(community): make mysql lifecycle migration retryable`）。
- 发布包 SHA-256 已在上传后校验；原部署目录已保留回滚副本。
- 目标 MySQL Alembic 版本已推进到 `20260812_0028 (head)`；社区评论生命周期字段和索引存在。
- API `live`、`ready`、`GET /api/v1/community/home`、Web `/community`、Admin `/login` 均已完成 HTTP 健康检查。

## 6. 后续

WP5-I3 的下一个业务切片为社区提及通知闭环；本轮只处理真实目标环境暴露的发布阻断项，
不扩张通知数据模型或 API 范围。
