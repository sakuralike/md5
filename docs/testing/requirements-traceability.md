# 需求—模块—测试追踪矩阵

- 更新日期：2026-08-10

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
| 用户账号与隐私中心 | `modules/auth`、`modules/account_privacy`、`apps/web` | `apps/api/tests/test_auth.py`、`apps/api/tests/test_n1_account_privacy.py`、`apps/web/src/services/account.test.ts`、`apps/web/src/services/account-privacy.test.ts`、`apps/web/src/services/auth.test.ts`：本人用户名修改、唯一冲突、幂等重放/冲突、统一一次性再认证凭据、当前密码与 TOTP 二次验证、会话族/操作目的绑定、过期与重放拒绝、其他会话撤销、TOTP 生成/确认/登录门禁/停用、邮箱验证与重发、忘记/重置密码、揭示历史最小披露、授权声明版本、导出所有权/过期/一次性下载、删除取消和到期去标识化 | N1 第 1～4 次本地切片完成；Web 密码/TOTP/会话/隐私浏览器 E2E 已闭环，邮箱变更、真实 Worker/目标环境和合规参数待后续 |
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
| Admin 工作流种子敏感数据控制 | `playwright.config.ts`、`tests/e2e/support/admin_session.ts`、`tests/e2e/support/seed_api.py` | 固定合成管理员/TOTP/案件/指纹；候选密码加密写入；旅程关闭截图/Trace | 本地策略和 9 项 Chromium 统一门禁完成；远端 CI `31294494635` 通过，目标环境待验收 |

## WP3 第 4 次开发迭代追踪增量（2026-08-09）

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| Web 密码修改与会话收口 | `apps/web/src/pages/AccountSecurityPage.vue`、`modules/auth`、`tests/e2e/support/seed_api.py` | `tests/e2e/web-account-security-journeys.spec.ts`：展示/撤销其他会话，修改密码后确认剩余非当前会话全部撤销 | Chromium 本地闭环完成；复制、过期会话组合和目标环境未验收 |
| Web TOTP 启停与登录门禁 | `AccountSecurityPage.vue`、TOTP 生成/确认/停用与登录 API | 绑定确认、无动态码登录拒绝、带动态码登录成功、再认证后停用 | Chromium 本地闭环完成；真实时钟漂移、恢复码和目标环境未验收 |
| Web 隐私授权、导出与删除撤销 | `apps/web/src/pages/AccountPrivacyPage.vue`、`modules/account_privacy` | 用途确认、个人数据一次性 JSON 下载、删除请求创建与撤销 | Chromium 本地闭环完成；真实 Worker 到期去标识化、合规参数和目标环境未验收 |
| Web 安全旅程敏感数据与限流控制 | `playwright.config.ts`、`tests/e2e/support/seed_api.py` | 三个隔离合成账号、两个不可登录刷新哈希、关闭截图/Trace、ESLint、E2E typecheck、Ruff、12 项 Chromium 旅程 | 本地定向检查及 `scripts/check.ps1 -SkipInstall -IncludeE2E` 统一门禁完成；远端 CI `31296867172` 五个作业通过，目标环境待验收 |

## WP3 第 5 次开发迭代追踪增量（2026-08-09）

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| Admin 用户停用、恢复与会话撤销 | `UserGovernancePage.vue`、`modules/admin/users.py`、隔离用户/会话种子 | `admin-governance-journeys.spec.ts`：一次性再认证、TOTP、结构化原因、停用并撤销 1 个会话、恢复账号 | Chromium 本地闭环完成；批量治理、紧急撤权和目标环境未验收 |
| 普通角色双人申请与批准 | `RoleChangesPage.vue`、`modules/admin/role_changes.py`、`role_change_requests` | 不同合成管理员创建/批准普通用户到可信贡献者请求，确认目标会话撤销和角色更新 | Chromium 本地闭环完成；拒绝组合、独立角色事件时间线和目标环境未验收 |
| Admin 治理敏感数据控制 | `playwright.config.ts`、`tests/e2e/support/seed_api.py` | 合成管理员/TOTP/用户/会话，关闭截图和 Trace；完整 14 项 Chromium 旅程 | 定向检查及 `scripts/check.ps1 -SkipInstall -IncludeE2E` 统一门禁完成；远端 CI `31298489273` 五个作业通过，目标环境待验收 |

## 2026-08-09 WP3 第 6 次迭代补充：系统配置与风险告警浏览器闭环

| 需求 | 实现证据 | 自动化证据 | 状态与剩余风险 |
|---|---|---|---|
| 系统配置草稿、发布与不可变回滚 | `SystemSettingsPage.vue`、`modules/admin/settings.py`、`system_setting_versions` | `admin-operations-journeys.spec.ts`：创建/发布两个版本、选择历史版本、MFA 再认证、创建并发布回滚版本 | Chromium 本地闭环完成；并发冲突浏览器组合和目标环境未验收 |
| 风险告警指派、核查与解决 | `RiskAlertsPage.vue`、`modules/risk_alerts/service.py`、风险告警事件与通知投影 | 隔离合成候选/证据/告警；指派 MFA 管理员、开始核查、确认处置并检查不可变时间线 | Chromium 本地闭环完成；失败通知重放浏览器组合、批量告警和目标环境未验收 |
| Admin 写操作成功反馈 | `SystemSettingsPage.vue`、`RiskAlertsPage.vue` | 浏览器断言草稿/发布/回滚、指派/核查/解决成功提示在详情刷新后仍可见 | 已修复并完成 Chromium 回归 |
| 配置与告警敏感数据控制 | `playwright.config.ts`、`tests/e2e/support/seed_api.py` | 合成管理员/TOTP/候选/证据/告警，候选密码加密写入，关闭截图和 Trace；完整 16 项 Chromium 旅程 | 定向检查及 `scripts/check.ps1 -SkipInstall -IncludeE2E` 统一门禁完成；远端 CI `31299937196` 五个作业通过，目标环境待验收 |

## 2026-08-09 WP3 第 7 次迭代补充：Web 身份与移动端键盘门禁

| 需求 | 实现证据 | 自动化证据 | 状态与剩余风险 |
|---|---|---|---|
| Web 邮箱一次性验证与状态刷新 | `VerifyEmailPage.vue`、`SecurityPage.vue`、`modules/auth/account_tokens.py`、隔离未验证用户/凭证种子 | `web-identity-journeys.spec.ts`：待验证状态、凭证消费、地址栏清理、重复消费拒绝、已验证状态 | Chromium 本地闭环完成；真实邮件链接、过期凭证和目标环境未验收 |
| Web 刷新令牌轮换与重放处置 | `modules/auth/service.py::rotate_refresh_token`、`core/browser_session.py`、隔离刷新会话种子 | HttpOnly Cookie 轮换、旧令牌重放返回 `auth.refresh_token_reused`、新访问令牌返回 `auth.session_revoked`、轮换后刷新令牌同族失效 | Chromium/APIRequest 浏览器上下文闭环完成；缺失 Cookie、自然过期和多标签页竞争组合待补充 |
| 邮箱验证页移动端与键盘操作 | `VerifyEmailPage.vue`、Shadcn-Vue `Button`/`Alert`/`Card` | 390 × 844 视口无横向溢出；返回登录链接可聚焦并由 Enter 激活 | 首个移动端/键盘门禁完成；其他 Web/Admin 核心页面、焦点顺序和错误提示可访问性待扩展 |
| 身份旅程敏感数据与限流控制 | `playwright.config.ts`、`tests/e2e/support/seed_api.py` | 合成一次性凭证仅以 SHA-256 摘要落库，合成刷新令牌仅保存摘要，关闭截图/Trace；不放宽生产每分钟 10 次登录限流；完整 19 项 Chromium 旅程 | `scripts/check.ps1 -SkipInstall -IncludeE2E` 统一门禁完成；远端 CI `31301934873` 五个作业通过，目标环境待验收 |
| Admin 候选审核 CI 重试稳定性 | `tests/e2e/admin-moderation-journeys.spec.ts` | 同一 Playwright 服务与数据库连续执行 2 次：首次完成审核，后续直接验证终态、原因码与说明 | 本地稳定性门禁通过；远端 CI `31302927800` 五个作业通过 |

## 2026-08-09 WP3 第 8 次迭代补充：视觉、可访问性与刷新竞争收口

| 需求 | 实现证据 | 自动化证据 | 状态与剩余风险 |
|---|---|---|---|
| Web/Admin 首批视觉与布局门禁 | `tests/e2e/support/visual_assertions.ts`、`admin-visual-accessibility.spec.ts`、`web-visual-accessibility.spec.ts` | 全页 PNG 报告附件、可见背景、关键区域正向边界、页面级无横向溢出 | 4 个核心页面首批完成；跨平台像素差异批准和更多页面待补充 |
| 键盘与错误提示可访问性 | `apps/admin/src/App.vue`、`apps/admin/src/pages/LoginPage.vue`、`apps/web/src/pages/LoginPage.vue` | 登录字段焦点顺序、可见焦点环、错误 `role=alert` 与 `aria-live=assertive` | 首批登录入口完成；复杂工作台键盘操作和屏幕阅读器实测待补充 |
| WCAG 自动扫描 | `@axe-core/playwright`、`expectNoSeriousAccessibilityViolations`、Web 对比度语义色修正 | WCAG 2 A/AA、2.1 A/AA 严重和关键违规为零 | Web 登录/首页、Admin 仪表盘/登录页通过；中等违规与全页面矩阵待评估 |
| 刷新令牌异常与竞争安全 | `modules/auth/service.py::rotate_refresh_token`、过期/并发会话种子 | 缺失 Cookie、自然过期、并发仅一次成功、竞争重放、访问与刷新令牌同族撤销 | SQLite 真实 API 闭环完成；MySQL 并发和高负载目标环境待验收 |
| WP3 第 8 轮回归 | Playwright 25 项 Chromium 旅程、API 身份回归、Admin SSR/Vitest | `pnpm e2e` 25/25；`test_auth.py` 11/11；Admin 52/52；ESLint/TypeScript/Ruff 与统一门禁通过 | 本地回归完成；远端 CI `31305403414` 五个作业通过 |

## 2026-08-09 WP3 第 9 次迭代补充：已登录核心页面无障碍与响应式收口

| 需求 | 实现证据 | 自动化证据 | 状态与剩余风险 |
|---|---|---|---|
| Web/Admin 跳过链接和主内容焦点目标 | `apps/web/src/App.vue`、`apps/admin/src/App.vue` | `web-authenticated-accessibility.spec.ts`、`admin-authenticated-accessibility.spec.ts`：Tab/Enter 跳转 | 本地 Chromium 完成；读屏器、Safari/Firefox/Edge 目标矩阵待验收 |
| Web 账号安全和隐私中心响应式验收 | `SecurityPage.vue`、`AccountPrivacyPage.vue` | Web 桌面/移动视觉基线、页面级无溢出、关键区域边界、全页 PNG、Axe 严重/关键扫描 | 本地闭环完成；贡献/信誉/活动/举报页面同类覆盖待补充 |
| Admin 用户治理和角色审批响应式验收 | `UserGovernancePage.vue`、`RoleChangesPage.vue` | Admin 桌面治理/移动审批视觉基线、无溢出、键盘跳转、Axe；筛选 SelectTrigger `aria-label` | 本地闭环完成；写操作全键盘流程和读屏器待验收 |
| 反馈播报和表单控件可辨识名称 | Web/Admin `aria-live`/`role`、Admin SelectTrigger aria-label | Axe 自动门禁；修复实际发现的 `button-name` 严重违规 | 本地严重/关键违规为零；中等违规和人工读屏器体验待验收 |
| E2E 合成状态隔离 | `tests/e2e/support/seed_api.py`、`web_session.ts`、`admin_session.ts` | 全量 28 项 Chromium 旅程在统一门禁通过；种子重建刷新 family，避免定向运行污染后续套件 | 本地统一门禁与远端 CI `31307983187` 五个作业通过；MySQL/Redis、并发压力与目标环境待验收 |

## 2026-08-09 WP3 第 10 次迭代补充：剩余业务页面无障碍矩阵收口

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| Web 贡献/信誉/案件/活动可访问性 | `SubmissionsPage.vue`、`ReputationPage.vue`、`TrustCasesPage.vue`、`web-authenticated-accessibility.spec.ts` | 桌面/移动无溢出、关键区域边界、全页 PNG、加载/错误/成功实时语义、Axe 严重/关键扫描 | 本地 Chromium 完成；读屏器、真实移动设备与跨浏览器待验收 |
| Admin 候选/案件/配置/告警可访问性 | `CandidateModerationPage.vue`、`TrustCasesPage.vue`、`SystemSettingsPage.vue`、`RiskAlertsPage.vue`、`admin-authenticated-accessibility.spec.ts` | 桌面/移动结构门禁、SelectTrigger 名称、候选页超宽回归、Axe 扫描 | 本地 Chromium 完成；全键盘写操作、读屏器和目标环境待验收 |
| Tailwind 内容扫描与语义变量 | `tailwind.config.js`、Web/Admin `index.css`、`packages/web-ui/src/styles.css` | 生产构建包含业务工具类；Axe 关闭登录页/配置页对比度问题 | 本地与 Linux CI 通过；跨 OS 字体与像素差异待批准 |
| 可诊断视觉断言 | `tests/e2e/support/visual_assertions.ts` | 失败输出越界元素、Axe 目标、HTML 摘要和失败原因 | 自动化完成；像素快照跨平台批准未执行 |
| 视觉/读屏器/浏览器验收策略 | `visual-baseline-strategy.md`、`screen-reader-checklist.md`、`browser-matrix.md` | 明确 Chromium 当前证据、Edge/Firefox/Safari/WebKit、NVDA/VoiceOver 和真实设备状态 | 策略已建立；外部/人工证据保持未验证 |
| WP3 第 10 轮回归 | `playwright.config.ts`、E2E 隔离种子 | 30/30 Chromium 旅程；`check.ps1 -SkipInstall -IncludeE2E`；远端 CI `31310591798` 五作业通过 | 本地与 Linux CI 自动化通过；目标环境和生产验收未关闭 |

## 2026-08-09 WP3 第 11 次迭代补充：Firefox 与 WebKit 跨引擎门禁

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| Playwright 三引擎项目 | `playwright.config.ts`、`package.json` | `e2e`、`e2e:firefox`、`e2e:webkit` 分别执行完整 30 项 | 本地 Chromium/Firefox/WebKit 共 90/90 通过 |
| 跨浏览器统一回归 | `scripts/check.ps1 -IncludeCrossBrowserE2E` | API/迁移/前端/Desktop 与三个浏览器隔离回归 | 本地统一门禁通过 |
| 远端浏览器矩阵 | `.github/workflows/ci.yml` | 三个浏览器独立安装、运行、重试和失败制品 | GitHub Actions `31319884808` 三个浏览器矩阵作业通过 |
| WebKit 与 Safari 边界 | `tests/e2e/support/accessibility.ts`、`browser-matrix.md` | WebKit 验证跳过链接聚焦和 Enter 激活；Chromium/Firefox 验证首次 Tab | WebKit 预检通过；真实 Safari Tab/VoiceOver 未验证 |
| 移动响应式跨引擎 | 三个移动视口 E2E 文件 | 去除 Firefox 不支持的 `isMobile`，保留固定视口、无溢出和键盘断言 | 三引擎预检通过；真实触摸设备未验证 |

## 2026-08-09 WP4 第 1 次迭代补充：安全审计与 SBOM 门禁

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| Python 生产依赖无已知漏洞 | `apps/api/pyproject.toml`、`security-gate.ps1` | `pip-audit --strict` JSON 报告；CycloneDX API SBOM | 本地及 CI `31322842317` 通过；数据库/系统包不在此门禁范围 |
| Node 高危/严重生产依赖阻断 | `pnpm-workspace.yaml`、`pnpm-lock.yaml` | `pnpm audit --prod --audit-level high`；修复 `nanoid` 3.3.16 | 高危 0、严重 0；中低风险后续纳入治理策略 |
| API 静态安全扫描 | `security-gate.ps1`、`apps/api/src` | Bandit 中高置信度的中高危结果阻断；JSON 报告 | 首批通过；前端 SAST、秘密扫描、DAST 和人工渗透待实施 |
| SBOM 与提交追溯 | `verify_security_artifacts.py`、Anchore SBOM Action | API/仓库 CycloneDX JSON、SHA-256 清单、`security-evidence-<commit-sha>` | 远端五份 JSON 已下载并复验；签名和生产来源证明待实施 |
| 安全门禁可重复执行 | `pnpm security:audit`、`check.ps1 -IncludeSecurity` | 4 项校验器单测、统一门禁、CI 独立作业 | 本地与远端通过；镜像扫描与限期豁免结构为下一轮 |


## 2026-08-09 WP4 第 2 次迭代补充：镜像、Secret 与限期风险豁免门禁

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| 最终镜像 HIGH/CRITICAL 默认阻断 | `container-images` CI 作业、三个 Trivy JSON | 首次运行 `31331415752` 阻断旧基础层；更新基础镜像后 `31331945963` 通过 | API/Web/Admin 均为 0；本机 Docker 引擎未运行，远端 CI 为实扫证据 |
| 已提交仓库 Secret 阻断 | Trivy filesystem secret scanner | 本地和远端 `trivy-repository-secrets.json` | Secret 0；本地 `.env` 和秘密托管平台不在仓库扫描范围 |
| 风险接受必须限期 | `security/risk-acceptances.json`、`verify_release_security.py` | 过期、重复、作用域不匹配、严重级别不匹配均阻断 | 当前接受记录 0 |
| 风险接受双人批准 | `owner`、`approved_by` 字段 | 同一主体负责与批准的合成测试失败 | 静态规则完成，正式审批流和电子签字未接入 |
| 镜像基础层维护 | `api.Dockerfile`、`frontend.Dockerfile` | 明确 Python/Node/Nginx 与 Alpine 版本并执行系统包安全更新 | 首批高危/严重项清零；后续由每次 CI 持续复扫 |
| 安全证据可复核 | `release-security-summary.json`、`RELEASE_SHA256SUMS` | 提交级制品下载后二次执行校验器 | `finding_count=0`、`accepted_count=0`、`blocking_count=0` |

## 2026-08-09 WP4 第 3 次迭代补充：API 动态安全与负向门禁

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| API 安全响应头一致 | `core/http_security.py`、`main.py` | `test_wp4_dast_security.py` 覆盖 200/401/405；DAST 响应头检查 | 自动门禁完成；上游网关/Nginx 目标环境复核待执行 |
| JSON 请求体资源限制 | `MAX_JSON_BODY_BYTES`、请求体缓冲上限 | `Content-Length` 与分块绕过负向测试；DAST 超大请求返回 413 | 默认 1 MiB，可配置 1 KiB～16 MiB；二进制制品保持独立流式限制 |
| 匿名对象与管理边界 | `/me`、隐私导出、管理员用户和审计接口 | API 定向测试与 DAST 均要求 401/标准错误码 | 匿名边界完成；已认证跨用户 BOLA 动态矩阵待补 |
| CORS 与方法滥用 | CORS 白名单、路由方法约束 | 可信预检 200、非信任预检 400、非法方法 405 且无 traceback | 首版完成；浏览器 Cookie CSRF/SameSite 待专项验证 |
| XSS/凭据不反射 | 合成查询、密码和令牌标记 | API 测试与 8 项 DAST 报告 | 响应最小披露完成；DOM XSS、集中日志和人工渗透待验证 |
| DAST 可重复与可追溯 | `pnpm security:dast`、`dast-security`、提交级制品 | 本地 8/8；GitHub Actions `31340260242` 九作业通过，远端报告 `failed=0` | 匿名 API 动态基线完成；不等同完整认证扫描或生产评估 |

## 2026-08-10 WP4 第 4 次迭代补充：认证对象边界与浏览器 Cookie 安全

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| 普通用户隐私导出对象隔离 | DAST 为用户 A 创建隐私导出，用户 B 读取同一 ID | `test_authenticated_object_boundaries_and_browser_cookie_csrf`、DAST `authenticated_object_boundaries` | 跨用户读取返回 `404 privacy.export_not_found`；更完整对象矩阵仍待补 |
| 普通用户会话撤销对象隔离 | 用户 A 会话族与用户 B 撤销请求 | 同一 API 测试、DAST `authenticated_object_boundaries` | 跨用户撤销返回 `404 auth.session_not_found`；管理员对象边界仍待补 |
| 浏览器刷新 Cookie 安全属性 | `core/browser_session.py` 既有 Cookie 策略由动态探针复核 | DAST `browser_cookie_csrf_samesite` | `HttpOnly`、`SameSite=Lax`、`Path=/api/v1/web/auth` 通过 |
| 浏览器 Cookie CSRF 来源校验 | 可信/不可信 Origin 的 refresh 请求 | API 定向测试与 DAST | 不可信来源 `403 request.invalid_origin`，可信来源刷新成功 |
| DAST 可重复与敏感材料隔离 | 唯一合成用户、Cookie 解析器仅在请求链中使用值 | 13 项脚本测试；本地 DAST `10/10`；CI `31349411600` | 报告不写入密码、令牌或 Cookie 值；管理员 MFA/重放/资源消耗仍未覆盖 |


## 2026-08-10 WP4 第 5 次迭代补充：管理员 MFA、再认证与幂等滥用门禁

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| 管理员 MFA 与高权限再认证 | 管理员路由、认证/TOTP 核心及 `test_wp4_dast_security.py` | DAST `admin_mfa_reauthentication`；错误当前密码拒绝、可信 Origin 登录和 `Cache-Control: no-store` | 动态门禁完成；更完整管理员对象矩阵和目标环境验收待补 |
| 再认证授权一次性消费 | 管理员状态变更授权存储与高权限入口 | `idempotency_replay_conflict` 验证已消费 token 再用于其他目标返回 `401 auth.invalid_reauthentication_token` | 一次性重放门禁完成；浏览器多标签竞争待补 |
| 管理员状态变更幂等 | 管理员状态变更与幂等核心 | 相同 `Idempotency-Key` 精确重放返回相同响应；请求内容变化返回 `409 request.idempotency_conflict` | 动态门禁完成；长时间并发/资源消耗待补 |
| 再认证失败限流与客户端退避 | `core/errors.py`、限流核心 | `admin_reauthentication_rate_limit` 与 `test_m1_security_gates.py` 验证 `429 rate_limit.exceeded` 和 `Retry-After` | 标准响应头完成；真实 Redis 恢复与跨实例一致性待补 |
| DAST 敏感材料隔离 | `dast_security_gate.py` 报告摘要结构 | 本地 `.local/security-dast-wp4-iteration-5b/dast-report.json` Secret 扫描通过；CI `31352246919` DAST 作业通过 | 本轮证据完成；认证爬虫、ZAP、人工渗透和生产评估不在本门禁范围 |


## 2026-08-10 WP4 第 6 次迭代补充：MySQL、Redis 与 Worker 恢复演练

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| MySQL 备份、清空与恢复 | `scripts/recovery-drill.ps1`、可配置 Compose 主机端口 | 真实 `mysqldump`、清空后表数 0、恢复后原合成账号登录；RPO 0.648 秒、RTO 17.648 秒 | 单节点 Compose 自动门禁完成；跨区域、保留策略和对象存储恢复待验收 |
| Redis 丢失降级与恢复 | `/health/live`、`/health/ready`、Redis 限流 fail-closed | outage 期间 liveness 200、readiness 503、认证限流 503；恢复后 readiness 200，RTO 8.908 秒 | 单实例故障门禁完成；集群切换和长故障待验收 |
| Worker 中断、重启与任务幂等 | Celery `privacy.build_export`、Worker Compose 存储卷和 `/tmp` Beat schedule | Worker 停止时任务 pending，重启后 ready；重复投递后 `privacy.export.ready` 仅 1 条，RTO 31.183 秒 | 隐私导出任务自动门禁完成；堆积、超时、死信和多 Worker 竞争待验收 |
| 恢复证据可机器复核 | `verify_recovery_evidence.py`、`recovery-drill-v1`、`recovery` CI 作业 | 3 项校验器测试；脚本测试全集 16 项；报告阈值、汇总和敏感字段拒绝 | 本地真实演练通过；CI 保存 30 天提交级制品 |


## 2026-08-10 WP4 第 7 次迭代补充：性能与可观测性

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| 精确查询 P95 ≤ 500 ms | `scripts/performance_probe.py` | 40 请求、10.043 QPS、P95 96.998 ms、0% 错误 | 本地隔离基线通过；目标 MySQL 环境待验收 |
| 短时 100 QPS | `scripts/performance-baseline.ps1` | 300 请求、99.808 QPS、P95 37.308 ms、0% 错误 | liveness 代码级基线通过；非业务容量结论 |
| HTTP/依赖/Worker 指标 | `core/observability.py`、`GET /api/v1/metrics` | 指标端点测试、性能报告可观测性检查 | 六类首版指标完成 |
| 低基数与敏感数据约束 | 规范化路由、`__unmatched__`、证据校验器 | 请求号/完整合成指纹不导出，敏感字段拒绝 | 本地自动化完成 |
| 请求关联 | `ContextVar`、`X-Request-ID`、JSON 完成日志 | 请求号回显和结构化脱敏测试 | API 单请求链路完成；分布式 Trace 待实施 |


## 2026-08-10 WP4 第 11 次迭代补充：多实例稳定性

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| 多 Worker 存活隔离 | `core/observability.py`、`worker.py` | FakeRedis 单测：2 个实例、清理 1 个后聚合仍可用 | 应用级心跳收口；目标监控平台实例发现待验收 |
| 单 Beat、多 Worker | `docker-compose.yml` 的 `scheduler` / `worker` 分离 | Compose 3 Worker 启动与实例数指标 | 本地隔离环境完成；编排平台副本策略待落地 |
| MySQL 连接池可配置 | `Settings`、`db/database.py`、`.env.example` | 非 SQLite 引擎参数传递单测、混合 MySQL 事务探针 | 应用配置完成；目标环境连接预算与慢查询待批准 |
| 单 Worker 故障不中断 | `multi-instance-stability-drill.ps1` | 3 → 2 时 `worker` 依赖仍为 1，补回后恢复 3 | 60 秒统一门禁通过；滚动发布和长时趋势待验收 |
| 混合稳定性证据 | `multi_instance_stability_probe.py`、证据校验器 | API 268、MySQL 272、Redis 279、Celery 270 次，合计 1089 次，零错误且队列清零 | 单机 Compose 门禁完成；MySQL/Redis HA 与生产容量不在本证据范围 |


## 2026-08-10 WP4 第 12 次迭代补充：Staging 长时稳定性准入合同

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| 至少 4 小时混合负载合同 | `infra/staging/readiness-profile.example.json`、`staging-readiness-plan.ps1` | 校验持续时长、采样周期、四类操作下限、P95/错误阈值与单 Worker 故障要求 | 参数合同完成；staging 实际执行待验收 |
| 显式 Worker 并发与连接池预算 | `.env.example`、`docker-compose.yml`、容量预算算法 | 默认 API `2 × 2`、Worker `3 × 2`、单 Scheduler；请求 `110` ≤ 允许 `136`，余量 `26`；超预算负向测试 | 静态预算完成；目标 MySQL 上限与慢查询趋势待实测 |
| MySQL/Redis 高可用证据声明 | `docs/runbooks/wp4-staging-readiness.md`、准入配置 HA 字段 | 拒绝 standalone/single 模式，要求 RTO/RPO、JSON 证据文件名和 Markdown 运行手册 | 证据合同完成；真实切换演练待执行 |
| 四方 Go/No-Go 审批 | `docs/templates/wp4-staging-go-no-go.md` | 精确要求 technical/security/operations/business 四个角色，缺失角色负向测试 | 模板与角色门禁完成；签字待目标环境证据 |
| 敏感证据拒绝 | `verify_staging_readiness_profile.py` | 递归拒绝 password/token/secret/key/credential 等敏感键和值 | 自动化完成 |
| 准入状态边界 | 生成计划 `contract-valid` / `not-run` / `pending-evidence` | 计划快照和 SHA-256 清单 | 合同验证完成，不等同于 4 小时运行或生产放行 |

## 2026-08-10 WP4 第 13 次迭代补充：资源趋势与 HA 执行证据合同

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| 资源趋势 schema | `infra/staging/resource-trend-report.example.json`、`verify_staging_execution_evidence.py` | 4 小时窗口、采样覆盖、四类操作量/P95/错误率、CPU/内存峰值和队列清零校验 | 合成合同夹具通过；目标环境采集待验收 |
| MySQL 连接预算 | `readiness-profile.example.json`、资源趋势校验器 | 峰值连接、允许连接和剩余余量精确匹配；超预算负向测试 | 机器校验完成；目标 MySQL 上限待实测 |
| MySQL HA 切换证据 | `mysql-ha-failover-report.example.json` | 主节点变化、读写恢复、数据一致性、幂等、RTO 42 秒/RPO 0 合成夹具 | schema 完成；真实切换待执行 |
| Redis HA 切换证据 | `redis-ha-failover-report.example.json` | 主节点变化、限流/Worker 恢复、队列清零、RTO 28 秒/RPO 0 合成夹具 | schema 完成；真实切换待执行 |
| 证据包完整性 | `staging-evidence-contract.ps1`、`staging-execution-evidence-summary.json` | 10 项校验器测试、profile SHA-256、6 文件 checksum、敏感字段拒绝 | 本地合成证据包 `contract-valid` |
| 执行状态边界 | `staging-execution-evidence-bundle-v1` | fixture 固定为 `not-run/pending-evidence`；target execution 最高进入 `pending-approvals` | 未宣称 staging/HA 已完成 |
