# SMTP 邮件投递工作台优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 参考 Zibll Email 设置，将 SMTP 邮件投递升级为可直接保存并立即生效的完整管理工作台，同时保证授权码加密、脱敏和审计。

**Architecture:** 在现有 `system_settings` JSON 设置表中增加 `smtp_email_delivery` 当前配置；数据库配置优先，缺失时回退环境变量。API 请求和 Worker 任务通过同一个解析器按需构造邮件 Gateway，避免固定启动时配置导致保存后必须重启。授权码使用部署密钥环派生的 AES-GCM 密文保存，响应只返回状态。

**Tech Stack:** FastAPI、Pydantic、SQLAlchemy、Python cryptography AES-GCM、Vue 3 Composition API、TypeScript、Shadcn-Vue、Tailwind CSS、Vitest、pnpm、PowerShell、Docker Compose。

---

## 文件结构与职责

| 路径 | 操作 | 职责 |
| --- | --- | --- |
| `apps/api/src/password_detective/core/settings_secrets.py` | 新增 | 提供配置授权码 AES-GCM 加密、解密和密钥版本处理。 |
| `apps/api/src/password_detective/modules/admin/email_delivery.py` | 修改 | 合并环境/数据库配置、校验保存请求、加密授权码、构建脱敏响应和审计摘要。 |
| `apps/api/src/password_detective/modules/admin/setting_schemas.py` | 修改 | 增加完整 SMTP 保存请求、脱敏响应和 HTML/连接参数校验。 |
| `apps/api/src/password_detective/modules/admin/router.py` | 修改 | 增加 `PUT /settings/email-delivery` 路由并注入数据库会话。 |
| `apps/api/src/password_detective/core/notifications.py` | 修改 | 支持动态主题前缀、底部文本、HTML 双格式和危险内容净化。 |
| `apps/api/src/password_detective/modules/auth/context.py` | 修改 | 为每个 API 请求从当前数据库配置解析 Notification Gateway。 |
| `apps/api/src/password_detective/worker.py` | 修改 | Worker 每次邮件任务从当前数据库配置构造 Gateway。 |
| `apps/api/tests/test_settings_secrets.py` | 新增 | 覆盖 AES-GCM、nonce、密钥版本和错误脱敏。 |
| `apps/api/tests/test_admin_email_delivery_settings.py` | 新增 | 覆盖 GET、PUT、权限、校验、保留/清除授权码、审计不泄密和立即生效。 |
| `apps/api/tests/test_notification_smtp.py` | 修改 | 覆盖主题、双格式正文、footer HTML 净化和密码不泄漏。 |
| `apps/api/tests/test_worker_email_delivery.py` | 新增 | 覆盖 Worker 从当前数据库配置读取 Gateway。 |
| `apps/admin/src/services/settings.ts` | 修改 | 增加读取、保存完整邮件配置的类型安全 API。 |
| `apps/admin/src/pages/SystemSettingsPage.vue` | 修改 | 按 Zibll 分组实现基础邮件、底部内容、SMTP 参数、状态与测试邮件表单。 |
| `apps/admin/src/pages/SystemSettingsPage.test.ts` | 修改 | 覆盖完整字段、保存/重置、授权码脱敏和测试反馈。 |
| `packages/api-contract/src/index.ts` | 修改 | 同步完整 SMTP 保存和响应契约。 |
| `packages/api-contract/src/index.test.ts` | 修改 | 防止敏感字段进入响应类型并验证保存请求字段。 |
| `项目文档/密码侦探社项目规格说明书-v3.0.md` | 修改 | 补充 SMTP 邮件投递工作台的配置、安全和验收要求。 |
| `项目文档/设计/2026-08-17-SMTP邮件投递工作台优化设计.md` | 新增 | 记录已确认架构和边界。 |
| `项目文档/实施计划/2026-08-17-SMTP邮件投递工作台优化实施计划.md` | 新增 | 记录实施任务和验证路径。 |
| `项目文档/文档变更记录.md` | 修改 | 记录需求、API、数据、安全、推送和 Staging 证据。 |

## Task 1：配置密文 AES-GCM

- [ ] 先写 `apps/api/tests/test_settings_secrets.py`：每次加密使用不同 nonce；当前密钥可解密；篡改密文、错误 key version 和超长值均失败且错误不包含明文。
- [ ] 运行 `pytest apps/api/tests/test_settings_secrets.py -q`，确认因实现不存在而失败。
- [ ] 新增 `settings_secrets.py`，使用现有应用密钥/密钥环派生配置专用 AES-GCM 密钥，关联数据绑定用途和 key version。
- [ ] 重跑定向测试，确认通过后提交 `feat(api): add encrypted settings secret vault`。

## Task 2：API 完整保存与动态解析

- [ ] 先写 `test_admin_email_delivery_settings.py`：GET 脱敏、PUT 保存、空授权码保持原值、显式清除、非法组合拒绝、审计不泄密。
- [ ] 运行定向测试确认新增行为失败。
- [ ] 增加经过 Pydantic 校验的保存模型；数据库配置使用 `SystemSetting(key="smtp_email_delivery")`，不存在时回退环境配置。
- [ ] 实现 `PUT /api/v1/admin/settings/email-delivery`，保存非敏感配置和 AES-GCM 密文；响应禁止原始授权码。
- [ ] 改造 API Gateway 依赖，使每次请求从数据库读取当前配置；测试中显式注入 Gateway 时保持覆盖优先级。
- [ ] 运行 API 定向测试并提交 `feat(api): persist smtp delivery settings securely`。

## Task 3：品牌邮件和双格式正文

- [ ] 先写 SMTP 失败测试：主题前缀来自保存配置；MIME 同时有纯文本和 HTML；危险 HTML 被净化；授权码不在 MIME。
- [ ] 运行 `pytest apps/api/tests/test_notification_smtp.py -q` 确认断言失败。
- [ ] 扩展 SMTP Gateway 的不可变品牌配置，保留现有通知类型 Header、幂等键和最小披露规则。
- [ ] 实现受限 HTML 净化与纯文本降级，统一覆盖测试邮件、账户令牌、风险告警、信任工单和社区摘要。
- [ ] 运行 SMTP 与通知回归测试并提交 `feat(api): support branded multipart smtp email`。

## Task 4：Worker 立即生效

- [ ] 先写 Worker 测试：数据库保存后，风险告警、社区摘要和信任工单任务使用最新配置而非启动时环境配置。
- [ ] 运行定向测试确认失败。
- [ ] 在邮件任务打开数据库会话后调用共享配置解析器构造 Gateway，释放数据库资源。
- [ ] 运行 Worker 和通知投递回归测试并提交 `fix(worker): reload smtp settings per delivery task`。

## Task 5：Admin Zibll 风格工作台

- [ ] 先更新渲染测试，要求出现发件人昵称、标题前缀、两段底部内容、SMTP 开关、服务器、端口、Auth、用户名、授权码、加密方式、超时和测试邮件入口。
- [ ] 运行 `pnpm --dir apps/admin test -- SystemSettingsPage.test.ts` 确认新增断言失败。
- [ ] 更新共享契约和服务函数，授权码只在提交请求中出现，不进入响应或持久化前端状态。
- [ ] 使用现有 Shadcn-Vue Input、Textarea、Switch、Label、Button 和 Tailwind 类实现分组、状态、显式清除、保存/重置和测试反馈，不修改生成 UI 组件源码。
- [ ] 运行 Admin 定向测试、typecheck、lint 和 build，并提交 `feat(admin): add full smtp delivery workbench`。

## Task 6：规格、门禁和发布

- [ ] 更新规格、设计/实施文档状态与文档变更记录，示例仅用合成值。
- [ ] 运行 API、Admin、契约、Worker 定向测试及 `pwsh -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1 -SkipInstall`。
- [ ] 运行 `pnpm --filter @password-detective/admin typecheck`、`pnpm --filter @password-detective/admin lint` 和相关构建。
- [ ] 执行 `git diff --check`、敏感值扫描，确认只包含本轮文件。
- [ ] 使用 `C:\Users\39859\.ssh\id_ed25519` 经 `ssh-release` 推送本分支和主线集成分支；不得使用普通 Push API。
- [ ] 读取 `E:\只比主题\minimax\服务器md5` 配置，按受控脚本部署 Staging；部署后核验 revision、HTTP、Worker、Alembic 和脱敏配置。
- [ ] 追加本地、远端、Staging 三层证据到 `项目文档/文档变更记录.md`。

## 计划自检

- 完整编辑、安全加密、保存立即生效、Worker 读取、Zibll 参考交互和测试邮件均有独立任务。
- 计划明确每个 TDD 红-绿循环、定向测试、提交边界和最终发布门禁。
- 没有新增版本历史、差异预览、发布、回滚或无关管理功能。
