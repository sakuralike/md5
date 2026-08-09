# 需求—模块—测试追踪矩阵

- 更新日期：2026-08-09

| 需求 | 模块 | 自动化证据 | 状态 |
|---|---|---|---|
| AUTH-01 | `modules/auth` | `apps/api/tests/test_auth.py`、`apps/api/tests/test_m1_security_gates.py`：注册、冲突、邮箱验证、非枚举重发 | M1 完成基础 |
| AUTH-02 | `modules/auth`、`core/browser_session` | `apps/api/tests/test_auth.py`、`apps/api/tests/test_m1_security_gates.py`：登录、轮换、摘要存储、重放、HttpOnly Cookie | M1 完成 |
| AUTH-03 | `modules/auth` | `apps/api/tests/test_auth.py`、`apps/api/tests/test_m1_security_gates.py`：会话列表、撤销、密码重置撤销、无访问令牌浏览器登出 | M1 完成 |
| AUTH-04 | `modules/auth/totp`、`modules/admin` | `apps/api/tests/test_m1_security_gates.py`：TOTP 绑定、密文存储、登录验证、MFA 声明、管理门禁 | M1 管理员基础完成；高风险动作二次验证在 M4 细化 |
| AUTH-05 | `core/rate_limit` | `apps/api/tests/test_security.py`、`apps/api/tests/test_m1_security_gates.py`：端点限流、跨实例 FakeRedis、真实 Redis 双客户端门禁 | M1 分布式基础与本地真实 Redis 门禁完成 |
| AUTH-06 | `core/security` | `apps/api/tests/test_auth.py`：Argon2id 哈希、错误密码拒绝 | M1 完成 |
| 关键写幂等 | `core/idempotency`、`modules/archives`、`modules/verification`、`modules/moderation`、`modules/trust_cases` | `apps/api/tests/test_m1_security_gates.py`、`apps/api/tests/test_m2_archive_core.py`、`apps/api/tests/test_m2_verification.py`、`apps/api/tests/test_m4_candidate_moderation.py`、`apps/api/tests/test_m4_trust_cases.py`：缓存响应、请求冲突、密码重置、贡献、反馈、人工状态处置和案件创建/转换 | M1/M2 基础完成；M4 候选与案件重复请求均不产生重复事件 |
| HASH-01～04 | `apps/web/src/services/fingerprint.ts`、`HomePage.vue` | `apps/web/src/services/fingerprint.test.ts`：SHA-256/MD5 分块、取消、进度、完整指纹格式识别 | M2 首版完成；Web Worker、超大文件性能和浏览器 E2E 待实施 |
| SEARCH-01～06 | `modules/archives` | `apps/api/tests/test_m2_archive_core.py`：完整指纹精确匹配、匿名/登录可见性、仅 verified 揭示、每日配额和审计 | M2 首版完成；已验证种子浏览器 E2E 与规模压测待实施 |
| SUB-01～06 | `modules/archives`、`modules/verification`、`core/candidate_secrets` | `apps/api/tests/test_m2_archive_core.py`、`apps/api/tests/test_m2_verification.py`、`apps/api/tests/test_security.py`：授权声明、持久化幂等、重复合并、密文与 HMAC、待结算及首次 verified 结算 | M2 核心完成；文件名元数据细化和更复杂风控留后续 |
| VERIFY-01～07 | `modules/verification`、`modules/moderation`、`modules/reputation` | `apps/api/tests/test_m2_verification.py`、`apps/api/tests/test_m4_candidate_moderation.py`、`apps/api/tests/test_m4_reward_compensation.py`、`apps/api/tests/test_m4_risk_alerts.py`、`apps/api/tests/test_m4_candidate_correlation.py`：单账号唯一有效反馈、不可变历史、关联键去重、候选内传递关联组、成功/失败维度动态限权、双成功验证、三失败隔离、verified 降级、自动/人工状态事件、人工首次验证结算、奖励撤销/恢复、15 分钟失败激增告警、规则版本、幂等和 rejected 普通反馈锁定 | M2 自动状态、M3 桌面签名回执及 M4 人工审核/奖励补偿/失败激增告警/候选内关联降权/通知 SLA 完成；跨候选图谱和动态处罚待实现 |
| 积分与信誉、用户中心 | `modules/reputation`、`modules/verification`、`apps/web` | `apps/api/tests/test_m4_reputation_center.py`、`apps/api/tests/test_m4_reward_compensation.py`、`apps/api/tests/test_m2_verification.py`、`apps/web/src/services/reputation.test.ts`：初始 50 分、积分状态投影、首次有效贡献/验证结算、引用幂等、0～100 边界、多轮撤销/恢复、原始事件不可变、本人私有读取和 Web 鉴权加载 | M4 积分/信誉中心与状态驱动补偿完成；管理员用户处置和动态信誉权重待实现 |
| DESK-01～08 | `apps/desktop-windows`、`modules/desktop_verification` | `apps/desktop-windows.tests/DesktopSecurityTests.cs`、`apps/desktop-windows.tests/ArchiveVerificationMatrixTests.cs`、`apps/api/tests/test_m3_desktop_verification.py`：DPAPI 身份持久化/重建、ECDSA DER 签名、规范载荷、加密 ZIP/7z 正确与错误密码、损坏/不支持格式、受控内容读取、资源限制、取消、路径穿越、最低版本详情、签名篡改、过期/重放、账号切换、撤销、时钟偏差和双独立回执 | M3 自动化核心与恢复 UX 完成；8 GiB 物理样本和 Windows 10/11 实机 E2E 待外部验收 |
| DESK-09～13 | `modules/desktop_updates`、`apps/admin`、`apps/desktop-windows` | `apps/api/tests/test_m3_desktop_updates.py`、`apps/admin/src/services/desktopReleases.test.ts`、`apps/desktop-windows.tests/DesktopUpdateClientTests.cs`：版本/目标选择、声明大小与摘要、原始制品上传、发布/撤回、生产签名元数据门禁、管理端元数据规范化与上传恢复、匿名检查、下载完整性、客户端查询参数和清单解析 | M3 后端发布通道、管理端发布闭环与显式升级入口完成；正式 Authenticode 流水线、分批发布和静默安装留后续 |
| 举报与申诉 | `modules/trust_cases`、`apps/web`、`apps/admin` | `apps/api/tests/test_m4_trust_cases.py`、`apps/web/src/services/trustCases.test.ts`、`apps/admin/src/services/trustCases.test.ts`：举报/申诉幂等创建、仅本人案件、贡献者和候选状态授权、关联目标约束、MFA 队列、受控状态/结果码、不可变事件和审计脱敏 | M4 统一候选举报与贡献者申诉首版完成；结果通知、SLA、账号申诉和候选状态联动待实现 |
| 风险告警 | `modules/risk_alerts`、`modules/verification`、`modules/correlation`、`core/notifications`、`apps/admin` | `apps/api/tests/test_m4_risk_alerts.py`、`apps/api/tests/test_m4_candidate_correlation.py`、`apps/api/tests/test_notification_webhook.py`、`apps/api/tests/test_notification_smtp.py`、`apps/admin/src/services/riskAlerts.test.ts`、`apps/admin/src/services/candidateModeration.test.ts`：三独立失败触发、活跃告警去重、候选内关联组与动态限权、SLA/指派、事务 Outbox、三次失败终态、投递指标/过滤、签名 Webhook、SMTP STARTTLS/SSL/认证/Message-ID、提供商回执、普通用户拒绝、MFA、持久化幂等重放、不可变事件、聚合最小披露与审计脱敏 | M4 失败激增、候选内关联降权、`risk-alert-sla-v1`、MFA 值班指派、`notification-webhook-v1`、SMTP 邮件和死信重放已完成；真实 SMTP 服务商/发件域名、最终送达回调、排班升级链、指标导出、跨候选图谱、动态规则和自动处罚待实现 |
| 管理端需求 | `modules/admin`、`modules/archives`、`modules/moderation`、`modules/trust_cases`、`modules/risk_alerts`、`modules/correlation`、`modules/desktop_updates`、`apps/admin` | `apps/api/tests/test_auth.py`、`apps/api/tests/test_m1_security_gates.py`、`apps/api/tests/test_n2_admin_dashboard.py`、`apps/api/tests/test_n2_admin_audit_logs.py`、`apps/api/tests/test_m4_candidate_moderation.py`、`apps/api/tests/test_m4_reward_compensation.py`、`apps/api/tests/test_m4_trust_cases.py`、`apps/api/tests/test_m4_risk_alerts.py`、`apps/admin/src/services/dashboard.test.ts`、`apps/admin/src/services/auditLogs.test.ts`、`apps/admin/src/pages/AuditPage.test.ts`、`apps/admin/src/pages/UserGovernancePage.test.ts`、`apps/admin/src/services/candidateModeration.test.ts`、`apps/admin/src/services/trustCases.test.ts`、`apps/admin/src/services/riskAlerts.test.ts`、`apps/admin/src/services/desktopReleases.test.ts`、`apps/admin/src/services/users.test.ts`：RBAC、普通用户拒绝、TOTP/MFA、真实仪表盘聚合、管理员专属用户治理列表/详情/统计、脱敏邮箱与最小披露、审计分页/筛选/详情/CSV 上限与公式注入防护、导出行为审计、时间窗口校验、最小披露审核详情、关联组与动态限权聚合、人工处置幂等/审计、奖励校正、风险投递指标/重放和桌面发布 | M1 安全入口、M3 桌面发布、M4 管理闭环和 N2 真实仪表盘/审计中心/用户治理只读总览三个切片完成；危险动作近期再认证、用户处置、系统配置和对象级批量接口待实现 |
| 用户账号与隐私中心 | `modules/auth`、`modules/account_privacy`、`apps/web` | `apps/api/tests/test_auth.py`、`apps/api/tests/test_n1_account_privacy.py`、`apps/web/src/services/account.test.ts`、`apps/web/src/services/account-privacy.test.ts`、`apps/web/src/services/auth.test.ts`：本人用户名修改、唯一冲突、幂等重放/冲突、统一一次性再认证凭据、当前密码与 TOTP 二次验证、会话族/操作目的绑定、过期与重放拒绝、其他会话撤销、TOTP 生成/确认/登录门禁/停用、邮箱验证与重发、忘记/重置密码、揭示历史最小披露、授权声明版本、导出所有权/过期/一次性下载、删除取消和到期去标识化 | N1 第 1～4 次本地切片完成；邮箱变更、浏览器 E2E、真实 Worker/目标环境和合规参数待后续 |
| 前端认证传输 | Web/Admin API Client | `apps/web/src/services/api.test.ts`、`apps/admin/src/services/api.test.ts` | M1 基础完成 |
| 敏感数据日志保护 | `core/logging`、`core/notifications`、`modules/moderation`、`modules/trust_cases`、`modules/risk_alerts`、`modules/correlation` | `apps/api/tests/test_security.py`、`apps/api/tests/test_m4_candidate_moderation.py`、`apps/api/tests/test_m4_trust_cases.py`、`apps/api/tests/test_m4_risk_alerts.py`、`apps/api/tests/test_m4_candidate_correlation.py`、`apps/api/tests/test_notification_webhook.py`、`apps/api/tests/test_notification_smtp.py`：嵌套字段递归脱敏；候选审核/关联详情不返回秘密材料、原始 IP 或安装哈希，通知管理响应不返回邮箱、Webhook 地址、签名密钥或载荷，人工处置审计不复制候选秘密、用户说明或管理员自由文本 | M2 日志基础与 M4 审核/案件/风险告警/关联分析/通知运维审计最小披露完成 |

真实 Redis 测试在普通单元测试中默认跳过；本地 Docker 双客户端门禁已通过，CI 仍通过 `RUN_REDIS_INTEGRATION=1` 和 Redis 服务显式启用。Docker 空环境已通过；生产 KMS 和托管分支保护仍属于外部环境验收，不以单元测试替代。

## N2 第 4 次迭代追踪增量

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| 管理员近期再认证 | `modules/auth/reauthentication.py`、`modules/admin/router.py`、`ReauthenticationPurpose.ADMIN_USER_GOVERNANCE` | `apps/api/tests/test_n2_admin_user_actions.py` | 已覆盖管理员专属、当前密码、TOTP、会话族/目的绑定、一次性消费、重放拒绝和 `no-store` |
| 用户停用与恢复 | `modules/admin/users.py`、`apps/admin/src/pages/UserGovernancePage.vue` | `apps/api/tests/test_n2_admin_user_actions.py`、`apps/admin/src/services/users.test.ts`、`apps/admin/src/pages/UserGovernancePage.test.ts` | 已覆盖原因码、预期状态、幂等、自动会话撤销、自身/受保护角色边界和最小披露审计 |
| 管理员撤销用户会话 | `modules/admin/users.py`、`apps/admin/src/services/users.ts` | `apps/api/tests/test_n2_admin_user_actions.py`、`apps/admin/src/services/users.test.ts` | 已覆盖预期活跃会话数、并发冲突、一次性凭据、幂等和审计 |
| 系统配置版本治理 | `modules/admin/settings.py`、`core/operational_settings.py`、`apps/admin/src/pages/SystemSettingsPage.vue` | `apps/api/tests/test_n2_admin_settings.py`、`apps/admin/src/services/settings.test.ts`、`apps/admin/src/pages/SystemSettingsPage.test.ts` | 已覆盖固定 Schema 校验、不可变草稿、差异、基线并发、配置目的再认证、幂等发布、运行时投影、审计最小披露和新版本回滚 |
| 受控角色变更 | 后端与 Admin 工作台闭环 | `modules/admin/role_changes.py`、`db/models/role_change_request.py`、`modules/admin/router.py`、`apps/admin/src/pages/RoleChangesPage.vue`、`apps/admin/src/composables/useRoleChanges.ts` | `apps/api/tests/test_n2_role_change_requests.py`、`apps/admin/src/services/roleChanges.test.ts`、`apps/admin/src/composables/useRoleChanges.test.ts`、`apps/admin/src/pages/RoleChangesPage.test.ts` | 固定普通角色转换矩阵、管理员双人复核、一次性再认证、状态/角色乐观并发、批准后会话撤销、幂等、审计、筛选分页、加载/空/错误态、详情和敏感凭据清理已实现；独立事件时间线、紧急撤权和批量处置待实现 |
| 批量处置与高级角色治理 | 未开放 | 无 | 待资源上限、角色层级配置化、紧急撤权和对象级批量模型冻结后实施 |
## WP1 第 1 次迭代追踪增量

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| Web/Admin ESLint 统一门禁 | `eslint.config.mjs`、根/Web/Admin `package.json` | `pnpm lint` | 已接入 Vue、TypeScript 和未使用代码检查，Shadcn-Vue 生成目录排除业务误报 |
| 业务 Vue 规范检查 | `scripts/check-frontend-policy.mjs`、`scripts/frontend-policy-baseline.json` | `pnpm lint` | 已阻止新增样式块、行内样式、十六进制颜色和原生表单控件；历史欠账 164 → 141 |
| 本地与 CI 统一入口 | `scripts/check.ps1`、`.github/workflows/ci.yml` | Windows PowerShell 5.1 统一门禁、GitHub Actions 前端任务 | 已接入 lint，并移除 PowerShell 7 专属空值条件访问语法 |
| 用户基础流程首批整改 | `apps/web/src/App.vue`、`pages/HomePage.vue`、`pages/RegisterPage.vue` | `apps/web/src/pages/HomePage.test.ts`、Web 类型检查/测试/构建 | 第一批完成；用户案件/信誉和 Admin 复杂页面仍待整改 |

## WP1 第 2 次迭代追踪增量

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| Web 积分与信誉页面规范整改 | `apps/web/src/pages/ReputationPage.vue`、Shadcn-Vue `Button`/`Progress` | `apps/web/src/pages/ReputationPage.test.ts`、Web 类型检查/测试/构建、`pnpm lint` | 已删除页面样式块、行内进度样式、硬编码颜色和原生按钮，保留积分/信誉只读业务语义 |
| Web 举报与申诉页面规范整改 | `apps/web/src/pages/TrustCasesPage.vue`、Shadcn-Vue `Button`/`Input`/`Label`/`Select`/`Textarea` | `apps/web/src/pages/TrustCasesPage.test.ts`、既有 `apps/web/src/services/trustCases.test.ts`、Web 类型检查/测试/构建、`pnpm lint` | 已删除页面样式块、硬编码颜色和原生表单控件，保留原因码、必填条件、幂等和本人案件边界 |
| 前端规范基线继续收紧 | `scripts/frontend-policy-baseline.json` | `scripts/check-frontend-policy.mjs` | 历史欠账 141 → 125，新增违规 0；剩余 6 个 Admin 页面待关闭 |

## WP1 第 3 次迭代追踪增量

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| Admin 登录页规范整改 | `apps/admin/src/pages/LoginPage.vue`、Shadcn-Vue `Button`/`Input`/`Label` | `apps/admin/src/pages/LoginPage.test.ts`、Admin 类型检查/测试/构建、`pnpm lint` | 已删除原生按钮与输入框，保留用户名/密码/TOTP 登录参数、忙碌态和错误反馈 |
| Admin TOTP 设置页规范整改 | `apps/admin/src/pages/TotpSetupPage.vue`、Shadcn-Vue `Button`/`Input`/`Label` | `apps/admin/src/pages/TotpSetupPage.test.ts`、Admin 类型检查/测试/构建、`pnpm lint` | 已删除原生控件和行内样式；配置 URI 使用 Tailwind 换行，密钥仍仅在设置流程内存中展示 |
| 前端规范基线继续收紧 | `scripts/frontend-policy-baseline.json` | `scripts/check-frontend-policy.mjs` | 历史欠账 125 → 117，新增违规 0；剩余 4 个 Admin 页面待关闭 |


## WP1 第 4 次迭代追踪增量

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| Admin 举报/申诉案件页面规范整改 | `apps/admin/src/pages/TrustCasesPage.vue`、Shadcn-Vue `Badge`/`Button`/`Input`/`Label`/`Select`/`Textarea` | `apps/admin/src/pages/TrustCasesPage.test.ts`、既有 `apps/admin/src/services/trustCases.test.ts`、Admin 类型检查/测试/构建、`pnpm lint` | 已删除页面样式块、硬编码颜色和原生表单控件，保留筛选、案件迁移、幂等和不可变事件时间线 |
| Admin 风险告警页面规范整改 | `apps/admin/src/pages/RiskAlertsPage.vue`、Shadcn-Vue `Badge`/`Button`/`Checkbox`/`Input`/`Label`/`Select`/`Textarea` | `apps/admin/src/pages/RiskAlertsPage.test.ts`、既有 `apps/admin/src/services/riskAlerts.test.ts`、Admin 类型检查/测试/构建、`pnpm lint` | 已删除页面样式块、硬编码颜色和原生表单控件，保留 SLA、指派、通知重放与处置闭环 |
| 前端规范基线继续收紧 | `scripts/frontend-policy-baseline.json` | `scripts/check-frontend-policy.mjs` | 历史欠账 117 → 60，新增违规 0；剩余候选审核和桌面发布 2 个 Admin 页面待关闭 |

## WP1 第 5 次迭代追踪增量

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| Admin 候选审核页面规范整改 | `apps/admin/src/pages/CandidateModerationPage.vue`、Shadcn-Vue `Badge`/`Button`/`Input`/`Label`/`Select`/`Textarea` | `apps/admin/src/pages/CandidateModerationPage.test.ts`、既有 `apps/admin/src/services/candidateModeration.test.ts`、Admin 类型检查/测试/构建、`pnpm lint` | 已删除页面样式块、硬编码颜色和原生表单控件，保留候选筛选、关联反馈降权、人工迁移、奖励调整和不可变时间线 |
| Admin 桌面发布页面规范整改 | `apps/admin/src/pages/DesktopReleasesPage.vue`、Shadcn-Vue `Badge`/`Button`/`Checkbox`/`Input`/`Label`/`Select`/`Textarea` | `apps/admin/src/pages/DesktopReleasesPage.test.ts`、既有 `apps/admin/src/services/desktopReleases.test.ts`、Admin 类型检查/测试/构建、`pnpm lint` | 已删除页面样式块、硬编码颜色和原生表单控件，保留 SHA-256、签名记录、制品上传恢复、发布和撤回边界 |
| WP1 前端规范债务清零 | `scripts/frontend-policy-baseline.json`、`scripts/check-frontend-policy.mjs` | 规范策略、Web/Admin lint/typecheck/test/build、Windows PowerShell 5.1 统一门禁 | 历史欠账 60 → 0，累计 164 → 0，新增违规 0；WP1 本地工程出口条件已满足 |
## WP2 第 1 次迭代追踪增量

| 需求 | 实现位置 | 验证证据 | 状态 |
|---|---|---|---|
| 账号申诉统一案件主体 | `apps/api/src/password_detective/db/models/trust_case.py`、`apps/api/alembic/versions/20260808_0019_wp2_account_appeals.py` | 迁移升级/降级/再升级；账号主体 API 集成测试 | 已实现第一轮 |
| 本人账号申诉创建 | `modules/trust_cases/router.py`、`service.py`、`schemas.py` | `apps/api/tests/test_wp2_account_appeals.py`：受控原因、恢复动作、服务端目标账号、限流入口、幂等 | 已实现第一轮 |
| 本人案件详情与对象级隔离 | `GET /trust/cases/{case_id}` | 本人 200、跨账号 404、未登录 401 | 已实现第一轮 |
| 最小披露审计 | `service.py::_audit_created` | 审计不含说明、证据摘要、处理自由文本；事件保留 request_id | 已实现第一轮 |
| 共享契约与调用层 | `packages/api-contract/src/index.ts`、`apps/web/src/services/trustCases.ts`、Web/Admin 案件页 | API contract/Web/Admin typecheck 与相关测试 | 已实现第一轮 |
| 指派、原子处置、重开、结果通知 | `modules/trust_cases`、通知 Outbox | 第 1 轮未实现；由第 2 轮拆分收口 | 部分实现 |

## WP2 第 2 次迭代追踪增量

| 需求 | 实现位置 | 验证证据 | 状态 |
|---|---|---|---|
| 案件版本乐观并发 | `trust_cases.version`、`_require_version`、`20260808_0020_wp2_case_assignment_reopen.py` | 指派/重开/状态转换携带 `expected_version`；过期版本返回 `409 trust.case_version_conflict` | 已实现本轮 |
| 独立案件指派/转派 | `modules/trust_cases/service.py::assign_case`、`router.py`、`apps/admin/src/pages/TrustCasesPage.vue` | 启用审核员/管理员校验；幂等重放；负责人前后事件快照；Admin 服务调用测试 | 已实现本轮 |
| 独立受控案件重开 | `modules/trust_cases/service.py::reopen_case`、`router.py`、`apps/admin/src/pages/TrustCasesPage.vue` | 仅 `resolved/dismissed` 可重开；清理负责人/结论元数据；幂等重放和过期版本测试 | 已实现本轮 |
| 原子处置与结果通知 | `modules/trust_cases` 的 `resolve` 编排、候选/账号副作用、`trust_case_effects`、通知 Outbox | `test_wp2_case_resolution.py`、`test_wp2_case_notifications.py`、Admin 服务/页面测试 | 第 3～4 轮本地闭环完成；正式 SMTP/Webhook、浏览器和目标环境验收未完成 |


## WP2 第 3～4 次开发迭代追踪增量（2026-08-08）

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| 案件原子最终处置 | `modules/trust_cases/service.py`、`POST /admin/trust-cases/{id}/resolve`、`trust_case_effects` | `test_wp2_case_resolution.py`、`test_m4_reward_compensation.py`、Admin `TrustCasesPage.test.ts` | 本地闭环完成；正式数据库、浏览器和生产验收未完成 |
| 账号/候选副作用与补偿 | `TrustCaseEffect`、候选状态事件、账号恢复、奖励/信誉校正 | `test_wp2_case_resolution.py`、`test_m4_candidate_moderation.py`、`test_m4_reward_compensation.py` | 本地闭环完成；跨服务恢复演练未完成 |
| 结果通知 Outbox | `trust_case_notifications`、`modules/trust_cases/notifications.py`、Celery 投递任务 | `test_wp2_case_notifications.py`、Admin `trustCases.test.ts` | 本地内存网关和失败重放完成；正式 SMTP/Webhook 送达未验收 |
| 案件 SLA 自动升级 | `sla_due_at`、`escalated_at`、`modules/trust_cases/sla.py`、Beat 60 秒任务 | `test_wp2_account_appeals.py` | 本地单案一次升级完成；值班排班/外部通知链未验收 |
| Web 本人账号申诉 | `apps/web/src/pages/TrustCasesPage.vue`、`createAccountAppeal` | `apps/web/src/pages/TrustCasesPage.test.ts`、Web typecheck/lint | SSR 基础渲染和类型门禁完成；浏览器交互 E2E 未验收 |

## WP3 第 1 次开发迭代追踪增量（2026-08-09）

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| 可重复浏览器测试基础设施 | `playwright.config.ts`、`scripts/e2e/start-api.mjs`、`tests/e2e/support/seed_api.py` | `pnpm e2e`、隔离 SQLite 重建、Web/Admin 独立端口 | 本地完成；目标 Compose/预生产环境未验收 |
| Web 认证核心旅程 | `tests/e2e/web-auth.spec.ts`、`web-guest.spec.ts` | 游客门禁、注册、自动登录、退出、重新登录 | Chromium 本地闭环完成；邮箱验证/刷新过期旅程待后续 |
| Admin 认证与 TOTP | `tests/e2e/admin-auth.spec.ts`、`admin-guest.spec.ts`、`TotpSetupPage.vue` | 游客门禁、首次 TOTP 绑定、动态码确认、MFA 二次登录 | Chromium 本地闭环完成；跨账号双人审批旅程待后续 |
| E2E 敏感制品控制 | 认证测试关闭截图/Trace、TOTP 读取后遮蔽、`.local/playwright` Git 忽略 | ESLint、E2E typecheck、Playwright 失败策略 | 本地策略完成；CI 失败制品仍需首轮远端运行复核 |
| CI 浏览器门禁 | `.github/workflows/ci.yml::e2e` | 安装 API/Chromium、`pnpm e2e`、失败证据上传 | 配置已实现；远端执行结果以本轮推送后 CI 为准 |

## WP3 第 2 次开发迭代追踪增量（2026-08-09）

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| Web 已验证查询、揭示、配额与页面清除 | `apps/web/src/pages/HomePage.vue`、`tests/e2e/support/seed_api.py` | `tests/e2e/web-core-journeys.spec.ts`：已验证查询、揭示最高可信候选、剩余配额和页面清除 | Chromium 本地闭环完成；复制、过期会话和目标环境未验收 |
| Web 授权贡献与待验证结果刷新 | `apps/web/src/pages/HomePage.vue`、`createContribution` | `tests/e2e/web-core-journeys.spec.ts`：未匹配指纹、授权声明、贡献提交、待验证候选刷新 | Chromium 本地闭环完成；重复贡献、本人贡献历史和目标环境未验收 |
| Web 候选举报与本人案件时间线 | `apps/web/src/pages/HomePage.vue`、`apps/web/src/pages/TrustCasesPage.vue`、`createTrustCaseReport` | `tests/e2e/web-core-journeys.spec.ts`：候选跳转、举报提交、待处理案件时间线 | Chromium 本地闭环完成；候选申诉、账号申诉、Admin 处置和通知送达未验收 |
| Web 核心旅程敏感数据控制 | `playwright.config.ts`、`tests/e2e/support/seed_api.py`、`tests/e2e/web-core-journeys.spec.ts` | E2E typecheck、ESLint、浏览器错误断言；种子候选密码加密写入 | 本地策略完成；远端 CI `31292352350` 通过，目标环境仍需复核 |
## WP3 第 3 次开发迭代追踪增量（2026-08-09）

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| Admin 候选人工审核与状态时间线 | `apps/admin/src/pages/CandidateModerationPage.vue`、`tests/e2e/support/seed_api.py` | `tests/e2e/admin-moderation-journeys.spec.ts`：SHA-256 筛选、审核说明、待验证到已验证和原因时间线 | Chromium 本地闭环完成；拒绝/隔离/恢复组合旅程和目标环境未验收 |
| Admin 举报案件指派、处理与解决 | `apps/admin/src/pages/TrustCasesPage.vue`、案件指派/转换/解决 API | `tests/e2e/admin-moderation-journeys.spec.ts`：案件筛选、负责人指派、开始处理、`admin.action_taken` 解决和不可变时间线 | Chromium 本地闭环完成；申诉/账号申诉、重开、通知重放组合旅程待后续 |
| 案件解决与关联候选原子副作用 | `modules/trust_cases`、`modules/moderation`、`TrustCasesPage.vue` | 解决举报后从候选审核页确认关联候选 `verified → quarantined` | 本地浏览器闭环完成；事务回滚已有 API 覆盖，目标 Compose 未验收 |
| Admin 案件操作反馈稳定性 | `TrustCasesPage.vue::openCase(preserveFeedback)` | 定向 Admin E2E 断言指派和解决成功状态；Admin 51 项测试通过 | 本地修复完成；视觉/屏幕阅读器反馈仍待可访问性轮次 |
| Admin 工作流种子敏感数据控制 | `playwright.config.ts`、`tests/e2e/support/admin_session.ts`、`tests/e2e/support/seed_api.py` | 固定合成管理员/TOTP/案件/指纹；候选密码加密写入；旅程关闭截图/Trace | 本地策略和 9 项 Chromium 统一门禁完成；远端 CI 与目标环境待回填 |
