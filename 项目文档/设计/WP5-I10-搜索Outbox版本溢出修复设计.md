# WP5-I10 搜索 Outbox 文档版本溢出修复设计

- 日期：2026-08-16
- 状态：已部署 Staging；UAT/Production 未批准
- 决策：方案 A（`BIGINT` 版本列）

## 1. 背景与已复现问题

Staging 在调用 `PATCH /api/v1/community/me/privacy` 时返回 HTTP 500。根因是 `update_privacy_preferences()` 调用 `enqueue_search_event()`，而资料来源没有业务 `version` 字段，`source_document_version()` 改用 `updated_at` 的微秒时间戳。该值约为 `1.7869e15`，超出 MySQL 有符号 32 位 `INTEGER` 的上限，导致 `community_search_outbox.document_version` 写入报错 1264。

`community_search_documents.document_version` 使用同一版本契约；即使仅扩大 Outbox，Worker 在索引投影写入文档时仍会遇到同类错误。因此两个列必须一起修复。

## 2. 目标与非目标

### 目标

1. 允许帖子版本和资料、板块、群组的微秒时间戳版本完整写入 MySQL。
2. 保持 Outbox 去重键、索引投影“较新版本优先”比较、重放和重建行为不变。
3. `PATCH /api/v1/community/me/privacy` 成功提交审计和搜索 Outbox 事件。
4. 保持 SQLite 自动化兼容，并验证 MySQL DDL 明确为 `BIGINT`。

### 非目标

- 不改变 `source_document_version()` 的版本生成规则。
- 不重写既有搜索 Worker、索引重建、隐私 API 或 Web 页面。
- 不修改已部署的 WP5-I10 私信实时事件协议。

## 3. 方案与决策

| 方案 | 描述 | 结果 |
|---|---|---|
| A | `community_search_outbox` 与 `community_search_documents` 的 `document_version` 同步升级为 MySQL `BIGINT` | **采用**；保留当前单调比较和去重语义，改动最小 |
| B | 将微秒时间戳压缩为 32 位整数 | 不采用；会引入碰撞、回退与并发排序语义风险 |
| C | 改为字符串或独立时间字段 | 不采用；会扩大比较、索引和重放契约的修改面 |

## 4. 数据与迁移契约

新增 Alembic `20260816_0046`，上游为 `20260816_0045`：

- `community_search_outbox.document_version`: `INTEGER` → `BIGINT`。
- `community_search_documents.document_version`: `INTEGER` → `BIGINT`。
- SQLAlchemy 两个模型列同时使用 `BigInteger`，避免新建数据库与迁移后数据库的类型漂移。
- 升级使用 `batch_alter_table`，保证 SQLite 测试和 MySQL 8 均由 Alembic 管理。
- 降级执行反向 `BIGINT` → `INTEGER`。一旦生产数据已写入超出 32 位范围的微秒版本，不允许依赖降级迁移截断数据；发布回滚使用本轮发布前的数据库备份。

## 5. 验收与发布

1. 先加入模型/MySQL DDL/迁移失败测试，确认当前 `INTEGER` 契约不满足要求。
2. 实现最小模型和迁移修复，测试转绿。
3. 验证隐私设置实际产生 `document_version > 2^31 - 1` 的搜索 Outbox 事件。
4. 执行 `20260816_0046 -> 20260816_0045 -> 20260816_0046` 隔离迁移往返、定向 API/搜索测试和前后端质量门禁。当前 worktree 的 `.venv` 布局不兼容 `check.ps1`（且复制修复后加载 `cryptography` Rust DLL 失败），因此未将该脚本作为本轮通过证据；同等子门禁已独立执行。
5. 推送远端等价树后部署 Staging，复验隐私设置 HTTP 200、Outbox 大整数版本、搜索投影、容器健康和长事务。

## 6. 安全与兼容性

版本值是内部索引顺序和去重元数据，不含正文、密文、令牌、密码或个人秘密。此修改不扩展 API 响应、日志内容或 Redis 载荷。


## 7. 实施与 Staging 证据（2026-08-16）

- 代码提交 `032f53790dffaaf6e58016c1c2f6f36f00d1cae7` 的 Git Tree `99cab018963bbb07f2f3c0b71314f3b5e3f70429` 已通过 Git Data API 同步为远端等价树提交 `82fef8257ab7d5eb885271b96d13cb63c67e290f`，`equivalent_tree=true`。
- 本地验证：9 项定向迁移/资料测试、完整 API `300 passed, 1 skipped`（覆盖率 88.26%）、SQLite `0046 -> base -> 0046` 实际往返、`pnpm lint`、`pnpm typecheck`、`pnpm test`（Admin 42 文件 87 项、Web 45 文件 78 项）及 `pnpm build` 均通过；构建仅保留既有 Vite 大块告警。
- Staging 修订 `82fef8257ab7` 使用备份 `/opt/password-detective-backups/20260816T210230Z-82fef8257ab7` 完成 MySQL `20260816_0046 (head)`。`community_search_documents.document_version` 与 `community_search_outbox.document_version` 均为 `bigint`。
- 服务器真实合成账号隐私设置返回 200，并生成 `document_version=1786914188170251` 的搜索 Outbox 事件；API 2、Worker 3、Scheduler 健康，长事务为 0。Web 代理 `/api/v1/health/ready` 为 200；未登录私信流与隐私设置均为 401。
- 本轮只更新 API、Worker、Scheduler 与 API 代理运行时；Web `password-detective-web:1a59275d042d` 和 Admin `password-detective-admin:4c3376e18840` 保持不变。UAT 与 Production 仍无批准证据。
