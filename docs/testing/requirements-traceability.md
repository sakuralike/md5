# 需求—模块—测试追踪矩阵

## 2026-08-11 当前验收基线

- 核心业务与 MVP 功能代码约 97%，本地工程与自动化准入约 99%，综合研发完成度约 89%，生产上线就绪度约 76%。
- 发布不要求人员签字；自动结论必须由 `automated-evidence-gate` 基于真实 `target-execution`、风险阈值、回滚检查、checksum 和候选提交生成。
- 桌面端不要求签名证书；上传和发布必须由服务端重算字节数与 SHA-256，并确认合法分发声明。
- 固定 4 小时 Staging 稳定性验证已按 2026-08-11 的当前决策移出必需验收，不再计为 P0；当前剩余重点是当前提交远端 CI、真实 MySQL/Redis HA 能力与切换证据、真实通知和实机兼容性。
- `target-execution` 封存包必须同时包含 MySQL/Redis 的脱敏 `target-observation` 能力报告；缺失或使用合同夹具时不得进入 `ready-for-release`。

- 更新日期：2026-08-11

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
| DESK-09～13 | `modules/desktop_updates`、`apps/admin`、`apps/desktop-windows` | `apps/api/tests/test_m3_desktop_updates.py`、`apps/admin/src/services/desktopReleases.test.ts`、`apps/desktop-windows.tests/DesktopUpdateClientTests.cs`：版本/目标选择、声明大小与摘要、原始制品上传、发布/撤回、合法分发确认/声明门禁、管理端元数据规范化与上传恢复、匿名检查、下载完整性、客户端查询参数和清单解析 | M3 后端发布通道、管理端发布闭环、SHA-256/大小完整性和合法分发声明完成；分批发布和静默安装留后续 |
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
| Web 授权贡献与待验证结果刷新 | `apps/web/src/pages/HomePage.vue`、`createContribution`、`modules/archives` | `test_m2_archive_core.py` 覆盖游客提交/幂等/无积分，`HomePage.test.ts` 覆盖游客入口与四人规则提示，`tests/e2e/web-core-journeys.spec.ts` 覆盖登录贡献与待验证候选刷新 | 游客与登录用户 Web 提交统一待验证；目标环境游客提交与晋级链路纳入本轮部署验收 |
| `verification-v3` 晋级门禁 | `modules/verification`、`modules/desktop_verification`、Alembic `20260814_0037` | `test_m2_verification.py` 覆盖前三人保持 pending、第四名独立用户晋级；`test_m3_desktop_verification.py` 覆盖签名桌面成功直入 verified | 本地 API 全量通过；目标 MySQL 迁移、游客入口与桌面直入纳入本轮部署验收 |
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
| Staging 混合负载合同 | `infra/staging/readiness-profile.example.json`、`staging-readiness-plan.ps1` | 校验默认 75 秒窗口、采样周期、四类操作下限、P95/错误阈值与单 Worker 故障要求 | 当前短时合同完成；固定 4 小时窗口已豁免 |
| 显式 Worker 并发与连接池预算 | `.env.example`、`docker-compose.yml`、容量预算算法 | 默认 API `2 × 2`、Worker `3 × 2`、单 Scheduler；请求 `110` ≤ 允许 `136`，余量 `26`；超预算负向测试 | 静态预算完成；目标 MySQL 上限与慢查询趋势待实测 |
| MySQL/Redis 高可用证据声明 | `docs/runbooks/wp4-staging-readiness.md`、准入配置 HA 字段 | 拒绝 standalone/single 模式，要求 RTO/RPO、JSON 证据文件名和 Markdown 运行手册 | 证据合同完成；真实切换演练待执行 |
| 自动 Go/No-Go 证据门禁 | `docs/templates/wp4-staging-release-decision.md`、`automated-evidence-gate` | 校验目标执行、风险阈值、回滚、checksum 和候选提交；不包含人员签字栏 | 自动门禁完成；最终结论待真实目标证据 |
| 敏感证据拒绝 | `verify_staging_readiness_profile.py` | 递归拒绝 password/token/secret/key/credential 等敏感键和值 | 自动化完成 |
| 准入状态边界 | 生成计划 `contract-valid` / `not-run` / `pending-evidence` | 计划快照和 SHA-256 清单 | 合同验证完成，不等同于目标 Staging 短时回归或生产放行；4 小时运行不再必需 |

## 2026-08-10 WP4 第 13 次迭代补充：资源趋势与 HA 执行证据合同

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| 资源趋势 schema | `infra/staging/resource-trend-report.example.json`、`verify_staging_execution_evidence.py` | profile 窗口、采样覆盖、四类操作量/P95/错误率、CPU/内存峰值和队列清零校验 | 短时合同夹具通过；目标 Staging 78 秒回归已完成 |
| MySQL 连接预算 | `readiness-profile.example.json`、资源趋势校验器 | 峰值连接、允许连接和剩余余量精确匹配；超预算负向测试 | 机器校验完成；目标 MySQL 上限待实测 |
| MySQL HA 切换证据 | `mysql-ha-failover-report.example.json` | 主节点变化、读写恢复、数据一致性、幂等、RTO 42 秒/RPO 0 合成夹具 | schema 完成；真实切换待执行 |
| Redis HA 切换证据 | `redis-ha-failover-report.example.json` | 主节点变化、限流/Worker 恢复、队列清零、RTO 28 秒/RPO 0 合成夹具 | schema 完成；真实切换待执行 |
| 证据包完整性 | `staging-evidence-contract.ps1`、`staging-execution-evidence-summary.json` | 10 项校验器测试、profile SHA-256、6 文件 checksum、敏感字段拒绝 | 本地合成证据包 `contract-valid` |
| 执行状态边界 | `staging-execution-evidence-bundle-v1` | fixture 固定为 `not-run/pending-evidence`；真实 target execution 全部通过后输出 `go` | 未宣称 staging/HA 已完成；不再依赖人员审批 |


## 2026-08-10 WP4 第 14 次迭代补充：目标环境采集与 HA 事件适配器

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| 目标执行源合同 | `materialize_staging_execution_evidence.py` 的资源/HA v1 schema | 严格执行组、UTC 时钟、采样和事件字段校验 | 工程入口完成；真实采集待执行 |
| 资源采样覆盖 | 资源样本、探针窗口、Worker 丢失/恢复事件 | 推导 profile 持续时长、样本覆盖率、最大间隔、四类操作和资源趋势 | 合成适配器合同通过；固定 4 小时持续时长已从当前验收移除 |
| HA 生命周期与回滚 | MySQL/Redis 依赖专属事件集合 | 切换触发、观测、主节点变化、应用恢复、数据/队列检查、回滚就绪的缺失/乱序负向测试 | 适配合同完成；真实 HA 待执行 |
| 脱敏与来源完整性 | 递归敏感字段拒绝、source SHA-256、执行组和采集器 provenance | 敏感键、凭据型值、跨执行组、合成适配器冒充 target 的拒绝测试 | 自动化完成 |
| 人工长时门禁入口 | `staging-target-execution.ps1` | readiness plan → 物化 → 最终校验 → checksum 一次完成 | 可人工触发；当前没有 target evidence |
| 状态边界 | `staging-target-adapter-contract.ps1` | 合同 fixture 强制断言 `contract-fixture / not-run` | 未宣称 staging、HA 或审批完成 |

## 2026-08-10 WP4 第 16 次迭代补充：证据包封存与审批交接完整性

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| 封存前完整性重验 | `scripts/seal_staging_evidence_archive.py`、`staging-evidence-archive-manifest-v1` | 六个主文件、主 checksum、来源 checksum、执行组、执行标识、profile 摘要和状态边界校验 | 工程合同完成；真实目标证据待生成 |
| 来源与目标提交绑定 | 封存清单 `source_files`、`candidate_commit`、`evidence_set_sha256` | 目标执行要求 40/64 位候选提交 SHA；fixture/synthetic/test/mock 适配器拒绝 | 目标候选交接规则完成；未绑定真实批准提交 |
| 确定性证据归档 | `staging-evidence-archive.zip`、manifest/ZIP detached SHA-256 | 固定 ZIP 时间戳、精确文件集合、嵌入清单和篡改检测测试 | 本地合同归档通过；不替代目标环境证据 |
| 发布状态边界（历史实现） | `staging-evidence-archive.ps1`、`docs/templates/wp4-staging-go-no-go.md` | 第 16 次迭代当时把 target 停在 `ready-for-approvals`；该规则已由第 22 次迭代的自动证据门禁替代 | 当前以 `ready-for-release` / 自动 Go-No-Go 为准，不要求人员签字 |


## 2026-08-11 WP4 第 22 次迭代补充：自动发布治理与桌面制品合法性

| 需求 | 模块 | 自动化证据 | 状态 |
|---|---|---|---|
| 发布无需人员签字 | `infra/staging/readiness-profile.example.json`、`scripts/verify_staging_readiness_profile.py`、`scripts/verify_staging_execution_evidence.py`、`scripts/seal_staging_evidence_archive.py` | `scripts/tests/test_verify_staging_readiness_profile.py`、`scripts/tests/test_verify_staging_execution_evidence.py`、`scripts/tests/test_seal_staging_evidence_archive.py`：只接受 `automated-evidence-gate`；目标执行校验后输出 `go`，封存交接为 `ready-for-release` | 已实现本轮；仍需真实目标执行证据 |
| 桌面制品完整性 | `modules/desktop_updates/service.py`、`desktop_releases` | `apps/api/tests/test_m3_desktop_updates.py`：上传和发布重新计算大小/SHA-256，错配拒绝；下载仅暴露已发布且完整制品 | 已实现本轮 |
| 桌面制品合法分发声明 | `DesktopReleaseCreateRequest`、Admin `DesktopReleasesPage.vue`、迁移 `20260811_0024_desktop_release_legality.py` | API/Admin 服务测试：未确认分发或声明不足时拒绝；发布审计保存声明 SHA-256 | 已实现本轮；声明不等同于外部法律意见 |
| N2 产品角色审批边界 | `modules/role_changes` | 既有 N2 专项测试 | 保持不变；本轮未移除产品权限治理的双人审批 |

## 2026-08-11 WP4 第 27 次迭代补充：HA 目标能力证据封存绑定

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| 真实 HA 能力证据不得脱离最终归档 | `scripts/seal_staging_evidence_archive.py`、`staging-evidence-archive-manifest-v1.ha_target_capabilities` | `target-execution` 强制要求 MySQL/Redis `target-observation`，能力摘要和文件 SHA-256 纳入 `evidence_set_sha256` | 已实现 |
| 能力文件完整性与类型边界 | `checksums.sha256`、`mysql-ha-target-capability.json`、`redis-ha-target-capability.json` | 缺文件、checksum 集合不完整、`contract-fixture` 冒充目标观察均拒绝 | 已实现 |
| 合同夹具不冒充正式验收 | `pnpm staging:evidence-archive-contract`、`pnpm staging:ha-capability-contract` | 合同归档继续输出 `contract-sealed / blocked-by-contract-fixture / not-run / pending-evidence`，且 `ha_target_capabilities` 为空 | 已实现 |
| 自动发布交接 | `handoff_status=ready-for-release`、`go_no_go_status=go` | 仅完整 `target-execution` 可进入自动发布结论，无人员签字依赖 | 工程闭环完成；真实目标证据待取得 |


## 2026-08-11 WP4 第 28 轮：生产秘密管理追踪

| 需求 | 代码/配置 | 自动化 | 结论 |
|---|---|---|---|
| 真实秘密不进入环境明文 | `config.py` 文件源、`docker-compose.production-secrets.yml` | `test_file_backed_settings.py`、Compose 合同门禁 | 工程通过 |
| 宿主机 root-only 文件可供非 root 应用读取 | `api-entrypoint.sh`、运行时 tmpfs、`su-exec` | 静态合同、Compose 渲染、本地 Docker 主进程降权烟测 | 本地运行通过，Linux 目标运行待验收 |
| 独立生产秘密和密钥环合法性 | `manage_production_secrets.py init/verify` | 初始化、占位值拒绝、密钥环/连接地址一致性测试 | 通过 |
| 加密备份完整性 | Scrypt + Fernet `.pdsb` | 明文缺失、错误口令拒绝、恢复字节一致 | 通过 |
| 安全轮换 | `rotate-candidate` + `rotate_candidate_secrets.py` | 轮换前备份、保留旧版本、恢复旧状态 | 工程通过，真实数据库 apply 待执行 |


## 2026-08-11 WP4 第 29 次迭代补充：完整用户等级系统

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| 等级与积分/信誉/角色分离 | `UserGrowthEvent`、`UserLevelProfile`、`levels.py` | `test_user_levels.py`、`test_m4_reputation_center.py` | 已实现；升级不改变 `UserRole` |
| 成长奖励幂等 | 登录日、验证贡献、有效验证业务引用唯一 | 重复登录、重复投影、自动晋级测试 | 已实现 |
| 奖励失效与恢复 | `adjustments.py` 追加 `growth.reward.*` 补偿 | `test_m4_reward_compensation.py` 净值与事件数量断言 | 已实现 |
| 等级规则治理 | `OperationalSettingsSnapshot.user_levels`、发布/回滚重建 | `test_n2_admin_settings.py` 顺序校验、规则发布、审计数量 | 已实现 |
| 服务端权益 | `require_submission_entitlement`、`daily_reveal_quota_for_user` | 提交拒绝、额度基线/等级提升测试 | 已实现 |
| 用户与管理界面 | Web `ReputationPage.vue`、Admin `SystemSettingsPage.vue` / `UserGovernancePage.vue` | Vitest 渲染/服务测试、TypeScript 检查 | 已实现 |

## 2026-08-12 WP5 社区完整功能规划追踪

| 需求 | 计划模块 | 计划自动化证据 | 当前状态 |
|---|---|---|---|
| COMMUNITY-14～31 | 社区首页、帖子、评论、统一可见性 | `test_community.py` 首页聚合、版本冲突、删除占位、两级回复和评论游标；三个独立页面渲染测试、详情治理渲染覆盖；Web typecheck/lint/Vitest | 部分实现：生命周期、评论游标、独立首页/详情/发布页和详情治理已落地；草稿、热门规则、提及通知、回复数重建和 Playwright 仍待开发 |
| COMMUNITY-32～35 | 点赞、收藏、可重建计数、失效引用清理 | 关系唯一约束、幂等重放、投影计数、私有收藏与不可见内容负向测试 | 本地编码和自动化完成，目标 MySQL/浏览器回归待部署 |
| COMMUNITY-36 | 点赞摘要通知 | Outbox 重试、聚合窗口、通知偏好和屏蔽关系测试 | WP5-I7 通知类型和偏好已预留，聚合生成仍未编码 |
| COMMUNITY-37～44 | 公开主页、关注/粉丝、屏蔽/静音 | `test_community_profiles.py`、关系页面渲染测试和统一门禁 | 本地已实现；目标 MySQL/浏览器部署回归待验证 |
| COMMUNITY-45～54 | 可配置板块、群组、成员和角色治理 | `test_community_groups.py`、`test_community_board_admin.py`、`test_community_board_seeding.py`、群组与管理配置页面渲染测试、Alembic 往返和统一门禁 | 本地代码与自动化已完成；默认板块已覆盖启动期与双实例并发初始化；目标 MySQL/浏览器部署回归待验证 |
| COMMUNITY-55～61 | 动态信息流 | `test_activity_feeds_and_reply_follow_notifications`、偏好未来事件测试、群组动态断言、Web 页面/服务测试 | 本地编码完成；目标 MySQL/浏览器部署回归待验证 |
| COMMUNITY-62～68 | 社区搜索 | `CommunitySearchProvider`、权限复核、Outbox 重放/续跑重建、管理最小披露测试；Web/Admin 渲染测试；Chromium、Firefox、WebKit 各 2 条定向 Playwright 旅程；`scripts/check.ps1 -SkipInstall` | 本地实现与统一门禁已完成：公开主题/用户/板块/公开群组、受限前缀降级、事务 Outbox、差异核对和健康聚合均有代码与自动化证据；目标 MySQL `ngram`、容量/降级演练、Staging、远端同步和发布验收仍未验证 |
| COMMUNITY-69～76 | 通知中心 | 通知去重、类型过滤、屏蔽、偏好、已读和 Web 页面测试 | 提及/回复/关注和站内/邮件偏好子集已实现；点赞、群组、私信/治理、邮件投递与 SSE 待后续 |
| COMMUNITY-77～93 | 一对一私信、实时增强、举报和直接互动一致性 | AES-GCM 密文、会话成员授权、幂等发送、持久事件、Redis 唤醒、独立 SSE、游标补偿、Web 收件箱/会话、三浏览器主旅程、非成员 404、最小披露治理测试；Staging 迁移、拓扑、HTTP、SSE 与镜像树复验 | COMMUNITY-77～83 与 COMMUNITY-85 的异步和实时基础已完成本地实现与自动化；WP5-I9 已有远端/Staging 证据，WP5-I10 远端/Staging 待本轮部署。COMMUNITY-84 消息举报、COMMUNITY-87 批量发送风控及治理收口仍待后续，UAT/Production 未验收 |

详细验收标准、数据模型、API 和迭代顺序见 `项目文档/密码侦探社社区完整功能开发计划-v1.0.md`；上述条目不计入当前完成度，直至代码、迁移、自动化和目标环境证据齐备。

## 2026-08-12 WP5-I3 第 2 个开发切片：独立社区页面路由

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| COMMUNITY-14～18、21～22、25、29～31 | `CommunityHomePage.vue`、`CommunityPostPage.vue`、`CommunityPostComposerPage.vue`、社区回复数写入修复与重建工具、Web 路由 `/community`、`/community/posts/:postId`、`/community/new` | 三个独立页面渲染测试、社区服务请求测试、回复数投影专项测试、移动端 Playwright、Web typecheck、ESLint、Vitest 30 项 | 部分实现：公开首页、详情、发布页、详情治理、举报、COMMUNITY-31 回复数投影修复及移动端主旅程已完成；真实目标环境回归和提及通知仍待完成 |
| 兼容回退 | `CommunityPage.vue`、`/community/legacy` | `CommunityPage.test.ts` | 已实现，旧综合页保留为回退入口 |

## 2026-08-12 WP5-I3 第 3 个开发切片：独立详情页治理能力

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| 主题作者编辑/删除 | `CommunityPostPage.vue`、`updateCommunityPost`、`deleteCommunityPost` | Web typecheck、ESLint、Vitest、统一门禁 | 已实现；采用 `expected_version` 和二次确认删除 |
| 评论作者编辑/删除 | `CommunityPostPage.vue`、`updateCommunityComment`、`deleteCommunityComment` | Web typecheck、ESLint、Vitest、统一门禁 | 已实现；删除保留结构占位 |
| 主题/回复举报 | `CommunityPostPage.vue`、`createCommunityReport` | Web typecheck、ESLint、Vitest、统一门禁 | 已实现；仅登录且邮箱验证用户可提交，Admin 负责处置 |

未验证项：目标环境 MySQL 回归和提及通知。移动端真实 API 主旅程已在第 5 个开发切片的 Chromium 390×844 触控视口执行。

## 2026-08-12 WP5-I3 第 4 个开发切片：回复数投影一致性

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| COMMUNITY-31 作者删除同步 | `service.delete_comment` 扣减 `reply_count`，重复删除返回 409 | `test_author_comment_delete_updates_reply_count_once` | 已实现并通过本地自动化 |
| COMMUNITY-31 治理移除同步 | `admin_service._remove_reported_content` 排除作者已删除占位 | `test_moderating_author_deleted_comment_does_not_double_decrement` | 已实现并通过本地自动化 |
| COMMUNITY-31 离线校验/重建 | `community/projection.py`、`scripts/rebuild_community_reply_counts.py` | `test_rebuild_community_reply_counts.py`，纳入 `scripts/check.ps1` | 已实现 dry-run 与显式 apply；目标 MySQL 执行仍待真实环境回归 |

## 2026-08-12 WP5-I3 第 5 个开发切片：移动端社区主旅程

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| COMMUNITY-14～18 登录后核心旅程 | 独立社区首页、发布页和详情页，以及既有社区创建/回复 API | `tests/e2e/web-community-mobile-journeys.spec.ts` 在 `web-chromium` 的 390×844 触控移动视口运行 | 已验证“登录 → 首页 → 发帖 → 详情 → 回复 → 返回首页”，并确认发布后的回复计数显示和首页主题回流 |
| COMMUNITY-21 合法发布边界 | 发布主题/回复的规则确认控件、验证后写入 | 同一 Playwright 主旅程勾选两次规则确认，并用合成文本写入 | 已验证合法授权确认参与前端提交条件；后端权限、限流和幂等继续由既有 API 测试覆盖 |
| 移动端错误观测 | 社区页面和真实 API 调用 | 同一用例执行 `observeBrowserErrors` / `expectNoBrowserErrors` | Chromium 主旅程无浏览器控制台错误；不替代 iOS/Android 真机或真实目标环境回归 |

未验证项：目标环境 MySQL 回归、真实目标浏览器/设备覆盖和提及通知。以上 Chromium 移动视口结果为本地自动化证据，不是生产验收结论。


## 2026-08-12 WP5-I3 第 6 个开发切片：MySQL 迁移与部署收口

| 追踪项 | 代码/迁移证据 | 测试或目标环境证据 | 状态 |
|---|---|---|---|
| COMMUNITY-14～31 目标 MySQL 迁移 | `20260812_0028_community_content_lifecycle.py` | 真实 MySQL 8.4 首次暴露 1093，修复候选重试后 `alembic current` 为 head | 已验证迁移修复 |
| MySQL 同表回填 | `UPDATE ... AS child INNER JOIN ... AS parent` | `test_mysql_backfill_uses_join_update` | 已实现 |
| 半执行迁移重入 | 反射已有字段、修订表、索引和外键后只执行缺失步骤 | `test_mysql_retry_after_non_transactional_ddl_only_runs_backfill` | 已实现 |
| 发布失败保护 | 迁移成功前不滚动替换 API/Web/Admin | 原运行容器持续健康；最终提交部署后执行完整 HTTP 复核 | 进行中 |

未验证项：提及通知和真实移动设备覆盖。目标 MySQL 的 COMMUNITY-14～31 数据结构迁移阻断已完成修复候选验证，最终状态以本轮提交重新部署后的统一验收为准。

## 2026-08-12 WP5-I3 第 7 个开发切片：社区提及通知

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| COMMUNITY-30 提及用户 | `service._sync_mention_notifications`、`community_notifications`、Alembic `20260812_0029` | 主题提及去重、自提及/未知用户过滤、回复提及测试 | 已实现主题/回复发布和编辑触发；屏蔽/提及偏好依赖后续社交关系模块 |
| COMMUNITY-36、69～76 通知与摘要投递 | `CommunityNotificationEmailDigest*`、`notification_service.py`、`notifications.py`、Worker、Admin 摘要聚合指标 | 邮件专属偏好/站内隔离、Memory/SMTP 摘要、迁移往返、完整 API 分片、前端 lint/typecheck/Vitest/build | 本地已实现并通过门禁；真实 Staging SMTP 接收、目标 MySQL/Redis 与容量验证待本轮部署后记录 |
| Web 通知中心 | `CommunityNotificationsPage.vue`、`/community/notifications`、`services/community.ts` | 页面渲染、认证头、URL 编码、幂等键、lint/typecheck/Vitest | 已实现 |


## 2026-08-12 WP5-I4 第 1 个开发切片：点赞与收藏

| 需求 | 代码证据 | 自动化证据 | 状态 |
|---|---|---|---|
| COMMUNITY-32 主题/回复点赞与取消 | 三张互动关系模型中的两张点赞事实表、PUT/DELETE like API | `test_post_and_comment_likes_are_idempotent_and_project_counts` | 已通过 |
| COMMUNITY-33 私有主题收藏 | `community_post_bookmarks`、本人收藏列表 API 和 `/community/bookmarks` | `test_bookmarks_are_private_paginated_and_removed_targets_are_cleanup_only`、`CommunityBookmarksPage.test.ts` | 已通过 |
| COMMUNITY-34 唯一关系和计数投影 | 数据库唯一约束、写后从事实表重新计数 | 重放同一幂等请求及重复关系测试 | 已通过 |
| COMMUNITY-35 移除内容互动约束 | 新增互动校验、取消互动保留、失效收藏返回空内容 | 后端负向测试覆盖新增阻断和清理成功 | 已通过 |
| COMMUNITY-36 点赞摘要通知 | `sync_like_summary`、邮件摘要关联项与投递前 `delivery_version` 复核 | `test_community_notification_email_digest.py`、SMTP 摘要测试 | 已实现本地闭环；真实 Staging SMTP 接收待部署后记录 |


## 2026-08-12 WP5-I5 第 1 个开发切片：公开主页与关系图谱

| 需求 | 代码证据 | 自动化证据 | 状态 |
|---|---|---|---|
| COMMUNITY-37 关注与取消关注 | `CommunityUserFollow`、PUT/DELETE `/community/users/{username}/follow`、唯一约束 | `test_follow_relationships_are_unique_and_private_lists_stay_private` | 已通过本地测试 |
| COMMUNITY-38～39 最小化公开主页 | `CommunityPublicProfile`、`GET /community/users/{username}`、公开内容投影 | `test_public_profile_update_privacy_and_safe_projection` | 已通过；禁止字段断言覆盖邮箱、活动、网络/设备、积分和策略 |
| COMMUNITY-40 隐私策略与关系列表 | `PATCH /community/me/privacy`、粉丝/关注列表访问控制 | 私有列表拒绝旁观者测试 | 已通过本地测试 |
| COMMUNITY-41 屏蔽强约束 | `CommunityUserBlock`、双向关注删除、提及策略与读取过滤 | `test_block_removes_follow_edges_and_prevents_follow`、内容读取过滤测试 | 已通过本地测试；私信通道待 WP5-I9 接入同一限制 |
| COMMUNITY-42 静音视图过滤 | `CommunityUserMute`、当前用户隐藏作者集合 | `test_block_and_mute_filter_existing_posts_from_read_paths` | 已通过本地测试 |
| COMMUNITY-43～44 计数投影和用户名策略 | 关注/粉丝投影重建、禁用用户过滤、认证用户名不可变 | 关系测试、`test_username_cannot_change_after_registration` | 已通过本地测试 |
| Web 路径 | 公开主页、关系列表、社区设置及资料链接 | `CommunityProfilePage.test.ts`、`CommunityRelationsPage.test.ts`、`CommunitySettingsPage.test.ts` | 已通过本地 Vitest；目标浏览器回归待部署 |


## 2026-08-12 WP5-I7 第 1 个开发切片：动态与通知偏好

| 需求 | 代码证据 | 自动化证据 | 状态 |
|---|---|---|---|
| COMMUNITY-55～59 三类动态和游标 | `CommunityActivityEvent`、`GET /community/activity`、读取时过滤 | `test_activity_feeds_and_reply_follow_notifications`、群组加入动态断言 | 本地通过 |
| COMMUNITY-60 未来事件偏好 | `CommunityActivityPreference`、GET/PUT 偏好 API | `test_activity_and_notification_preferences_only_affect_future_events` | 本地通过 |
| COMMUNITY-61 最小摘要和失效 | 180 字摘要、源引用、内容/账号/群组状态过滤 | 动态与既有私密群组负向测试 | 本地通过 |
| COMMUNITY-69～72 回复/提及/关注 | 通知类型扩展、唯一业务键、类型过滤、已读 API | 通知分类、去重、未读、越权和 Web 测试 | 当前子集通过 |
| COMMUNITY-73 偏好 | 通知偏好表、GET/PUT API、Web 偏好矩阵 | 后端持久化与 Web service/render 测试 | 站内生效；邮件投递待实现 |
| COMMUNITY-76 屏蔽边界 | 通知写入和动态读取复用 block/mute | 社交关系和动态专项测试 | 普通互动通过；治理通知待生成后补测 |

## 2026-08-13 后台 Logo 与设置布局追踪

| 需求 | 代码证据 | 自动化证据 | 状态 |
|---|---|---|---|
| Logo 图片上传 | `site/assets.py`、`POST /admin/settings/logo`、`uploadSiteLogo` | `test_admin_can_upload_and_serve_content_addressed_site_logo`、`settings.test.ts` | 已实现 |
| 文件安全与公开读取 | 类型/签名/大小校验、哈希文件名、公开 FileResponse、不可变缓存 | 类型不匹配与 SVG 拒绝测试、公开响应头断言 | 已实现 |
| 后台设置导航修复 | `App.vue` 将桌面侧栏移出模糊顶栏，`AdminSettingsNavigation.vue` 桌面/移动模式 | `App.test.ts` 固定视口定位和主内容留白断言 | 已实现 |
| 等级权益横向布局 | `SystemSettingsPage.vue` 横向 flex、snap、overflow 列表 | `SystemSettingsPage.test.ts` 横向列表语义与类名断言 | 已实现 |
| 容器持久化 | `site-asset-data`、`SITE_ASSET_STORAGE_PATH`、Nginx 3 MB 限制 | Compose 配置校验与目标部署冒烟 | 待本轮服务器验证 |

## 2026-08-14 WP5-I7 通知可靠性第一轮追踪

| 需求 | 代码证据 | 自动化证据 | 状态与剩余风险 |
|---|---|---|---|
| 事务 Outbox 与幂等投递 | `CommunityNotificationOutbox`、迁移 `20260814_0035_community_notification_outbox.py`、`notification_service.py` | `test_notification_outbox_dispatch_and_replay_cursor`、Ruff、迁移往返 | 已实现数据库事实与待投递事件同事务提交；邮件通道和 Admin 失败重放尚未实现 |
| Worker 重试与投递前权限复核 | `worker.py` 的 Beat/Task、`dispatch_pending_notification_events` | 社区服务测试、统一门禁、目标环境 Worker 状态 | 已实现有限指数退避、终态错误码、偏好/屏蔽/主题可见性复核；指标导出与人工重放待后续 |
| SSE 事件流与断线补偿 | `notification_stream.py`、`router.py`、`CommunityNotificationStream*` | API 测试、Web `communityNotificationStream.test.ts`、公网 curl/浏览器验收 | 已实现 ready/notification、心跳、`Last-Event-ID`、跨用户隔离和失效主题过滤；多实例 Pub/Sub 优化待后续 |
| Web 全局未读入口 | `useCommunityNotificationStream.ts`、`App.vue`、`UserAccountMenu.vue` | Web Vitest、typecheck、真实 Chromium 旅程 | 已实现初始快照、实时未读、断线重连和用户会话游标；通知中心列表实时插入/分页合并待后续 |

本切片只推进网页端；桌面端 UI 尚未设计冻结，不纳入本轮新增范围。上述本地证据不能替代真实 SMTP 送达、多实例 Redis、目标环境迁移和发布回滚证据。


## 2026-08-14 WP5-I7 通知可靠性第二轮追踪

| 需求 | 代码证据 | 自动化/验收证据 | 状态与剩余风险 |
|---|---|---|---|
| Web 通知共享状态 | `stores/communityNotifications.ts`、`useCommunityNotificationStream.ts` | Store 单元测试、Web typecheck/lint/Vitest | 全局账户菜单与通知中心共用未读数、连接状态和最新事件 |
| 通知中心实时插入与去重 | `CommunityNotificationsPage.vue`、`mergeCommunityNotificationItems` | 去重、覆盖更新、稳定倒序测试；真实浏览器关注通知旅程 | 已实现类型筛选内实时插入和“实时收到”标识 |
| 快照与 SSE 并发保护 | 加载前后 `eventRevision` 比较、实时项保留合并 | 统一门禁与 Staging 无刷新通知验收 | 已防止列表旧快照覆盖请求期间收到的新事件；复杂多标签页同步待后续 |
| 已读状态全局同步 | 单条/全部已读后更新共享 Store | 页面操作与全局未读数验收 | 当前标签页闭环完成；跨标签广播待后续 |

本切片仍不包含邮件摘要真实投递、Admin Outbox 失败查询/受控重放、Redis Pub/Sub 多实例优化和桌面端通知 UI。

## 2026-08-14 本轮需求追踪补充

| 需求 | 实现证据 | 当前状态 | 未验证项 |
|---|---|---|---|
| 总哈希值池 | `apps/api/src/password_detective/modules/hash_pool/`、`apps/admin/src/pages/HashPoolPage.vue`、`GET /api/v1/admin/hash-pool` | 已实现，定向测试、统一门禁及 Staging 受保护路由冒烟通过 | 已登录真实浏览器和生产级数据量验证 |
| 用户审批手动创建用户 | `AdminUserCreateRequest`、`POST /api/v1/admin/users`、`UserGovernancePage.vue` | 已实现并有服务/API/页面测试，Staging 页面制品已部署 | 已登录目标环境权限和审计查询验证 |
| 用户等级与权益归属 | `UserLevelsManagement.vue`、`/users#user-levels` | 已移至用户审批，生成不可变草稿 | 发布门禁和真实浏览器滚动定位 |
| Web 右下角公告弹窗 | `AnnouncementPopup.vue`、`services/announcements.ts`、`tests/e2e/web-announcements.spec.ts` | 已实现；Chromium、Firefox、WebKit 均完成自动关闭、手动关闭、localStorage、图片加载和外链点击真实旅程 | Staging 公网图片缓存与目标 Windows 实机联调 |
| 桌面公告读取 | `DesktopApiClient` 基址补全、no-cache 请求、默认代理地址 | 已实现并有 29 个 Windows 测试，公网代理公告接口 HTTP 200 | Release 包在目标 Windows 实机验证 |


## 2026-08-15 Web 公告图片与外链真实验收追踪

| 需求 | 模块 | 自动化证据 | 状态 |
|---|---|---|---|
| ANN-WEB-IMAGE-01 Admin 上传并保存公告图片 | `WebAnnouncementsPage.vue`、`POST /admin/web-announcements/images` | Admin Chromium/Firefox/WebKit E2E 上传合成 PNG，校验 MIME、字节数、SHA-256、预览、保存和发布 | 已实现；Staging 公网资源缓存待验证 |
| ANN-WEB-IMAGE-02 Web 弹窗图片加载与点击外链 | `AnnouncementPopup.vue`、专用图片资源路径 | Web Chromium/Firefox/WebKit E2E 校验图片 `naturalWidth > 0`，点击后打开配置的 HTTP(S) 外链 | 已实现；目标 Windows 桌面端图片联动不在本轮范围 |
| ANN-WEB-E2E-03 跨浏览器公告状态隔离 | `tests/e2e/support/web_announcements.ts`、Vite API 代理环境变量 | 三浏览器各 37 项 E2E；WebKit 首次单项时序抖动复跑通过 | 已实现；后续保留稳定性观察 |

## 2026-08-14 公告渠道隔离追踪

| 需求 | 模块 | 自动化证据 | 状态 |
|---|---|---|---|
| ANN-CHANNEL-01 桌面/Web 公告完全分离 | `desktop_announcements`、`web_announcements`、Admin 双入口、独立资源目录 | `apps/api/tests/test_m5_desktop_announcements.py`、`apps/api/tests/test_m5_web_announcements.py`、`apps/admin/src/pages/WebAnnouncementsPage.test.ts`、跨浏览器 Admin/Web E2E | 已实现；Chromium、Firefox、WebKit 真实浏览器 E2E 通过 |
| ANN-WEB-02 Web 自动关闭时间 | `auto_close_seconds`、`AnnouncementPopup.vue`、`announcementContent.ts` | `apps/api/tests/test_m5_web_announcements.py`、`apps/admin/src/services/webAnnouncements.test.ts`、`apps/web/src/components/AnnouncementPopup.test.ts`、`apps/web/src/lib/announcementContent.test.ts`、跨浏览器 Web E2E | 已实现；Chromium、Firefox、WebKit 自动关闭、手动关闭与 localStorage 旅程通过 |

## 2026-08-15 Web 公告图片与外链 Staging 收口

- `7531c634188a` 已推送到 `codex/m5-entry-gates` 并部署到 Staging；API 2、Worker 3、Web、Admin、Scheduler 和监控服务均运行正常，迁移为 `20260814_0039 (head)`。
- 服务器本机 `ready`、桌面公告、Web 公告接口均 HTTP 200；公网 Web `:5173`、Admin `:5174` 及其 `/api/v1` 代理同样 HTTP 200。
- 公网 `:8000` 直连仍为 HTTP 502，标记为独立入口配置风险；不改变当前 Web/Admin 代理路径的通过结论。

## 2026-08-16 WP5-I9 第 3 个开发切片：私信隐私生命周期治理

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| COMMUNITY-77～93 导出边界 | `build_privacy_export` 仅查询请求人参与的私信会话；导出 `direct_conversations` 与 `direct_messages` 时只投影公开身份、正文、序号和时间 | `test_privacy_export_contains_only_requesters_direct_message_records`；断言不含 `ciphertext` | 本地已实现并通过定向测试；目标环境导出回归待部署 |
| COMMUNITY-77～93 删除清理 | `process_due_deletion_requests` 按通知 Outbox、通知、消息、成员、会话顺序清理私信数据；不把正文写入审计详情 | `test_account_deletion_removes_direct_message_rows`；断言消息、成员、会话、私信通知和 Outbox 清零 | 本地已实现并通过定向测试；目标环境删除回归待部署 |
| I9 全闭环状态 | 加密、授权、幂等、通知、导出/删除、Web 收件箱和会话页面均已实现 | 私信专项 API、N1 隐私、CORS、Web 单元测试；Chromium/Firefox/WebKit 私信旅程 3/3；统一门禁 Chromium Web/Admin 42/42、Desktop 29/29 | 本地闭环完成；远端和 Staging 证据在本轮发布后补记，UAT/Production 未完成 |


## 2026-08-16 WP5-I10 私信实时事件本地追踪

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| COMMUNITY-85 持久事件 | `CommunityDirectStreamPosition`、`CommunityDirectEvent`、Alembic `20260816_0045`、消息/已读同事务事件 | 本地迁移测试；Staging MySQL 已到 `20260816_0045 (head)`，发布备份为 `/opt/password-detective-backups/20260816T173933Z-1a59275d042d` | 已验证 |
| Redis 跨实例唤醒与降级 | `direct_message_realtime.py`、提交后 `_publish_direct_conversation_wakeups`、数据库轮询补偿 | Staging API-2 发送、API-1 接流，Redis 唤醒 0.108 秒；停止 Redis 后数据库补偿 0.005 秒，随后 Redis 恢复健康 | 已验证；事件载荷无敏感字段 |
| 独立私信 SSE | `GET /api/v1/community/direct-messages/stream`、function-scope 认证、`Last-Event-ID`、`ready/reset_required` | 本地游标与 Session 测试；Staging 未登录 401、授权 `ready`、跨实例事件和 `Last-Event-ID` CORS 预检 200 | 已验证；长事务为 0 |
| Web 实时状态 | 独立服务、组合式函数、Pinia Store、App 生命周期、账户菜单/收件箱/会话页 | Web 45 文件 78 测试；Chromium/Firefox/WebKit 3/3；Staging Web 制品含实时游标标记，公网首页与消息页 200 | 已验证 Staging 制品与入口；UAT 仍未验收 |
| 证据边界 | 本地、远端、Staging、UAT/Production 分层记录 | 本地统一门禁通过；远端提交 `1a59275d042d` 与本地 tree `72337848988a` 等价；Staging 修订独立复验通过 | Staging 通过不等于 UAT/Production；隐私设置 Outbox 溢出缺陷单独跟踪 |


## 2026-08-16 搜索 Outbox 文档版本溢出修复追踪

| 需求/风险 | 实现证据 | 自动化与目标环境证据 | 当前状态 |
|---|---|---|---|
| 搜索版本 64 位存储 | `CommunitySearchDocument`、`CommunitySearchOutbox` 的 `document_version` 使用 `BigInteger`；Alembic `20260816_0046` 同步修改两张表 | MySQL DDL/模型/迁移测试；完整 API `300 passed, 1 skipped`；Staging `information_schema` 显示两列均为 `bigint` | 已验证 |
| 隐私设置搜索入队 | `update_privacy_preferences()` 保持现有微秒版本与 Outbox 去重语义 | 资料 API 回归断言 Outbox `document_version > 2_147_483_647`；Staging 合成账号 `PATCH /api/v1/community/me/privacy` 为 200，写入 `1786914188170251` | 已验证 |
| 投影侧兼容性与回滚 | 搜索文档列与 Outbox 同时扩宽，避免 Worker 投影再次溢出；降级声明保留 | SQLite 实际往返；目标回滚需使用发布前数据库备份，不得将已写入的大整数截断为 32 位 | 已验证修复；UAT/Production 未批准 |

## 2026-08-17 WP5-I7 真实邮件摘要投递（方案 B）

| 需求 | 代码证据 | 自动化/验收证据 | 状态与剩余风险 |
|---|---|---|---|
| 独立站内/邮件通道 | `notification_channels`、`in_app_notification_visibility_condition`、通知读取/已读/SSE 过滤 | 邮件专属偏好创建摘要、不创建站内事件；历史站内事件在切换为邮件专属后不再可列出、计未读或标记已读 | 本地已通过；Staging 运行时待复验 |
| 持久化摘要与可靠投递 | `community_notification_email_digests`、`community_notification_email_digest_items`、Worker 任务、稳定 Message-ID | Memory 与 SMTP 最小披露摘要测试；SQLite `upgrade head -> downgrade -1 -> upgrade head` | 本地已通过；真实 SMTP 接收待安全测试收件人和 Staging 配置确认 |
| 运营与隐私 | Admin 摘要批次聚合指标、隐私删除时按收件人清理摘要批次 | 后端 API 全量分片、前端 lint/typecheck/Vitest/build | 本地已通过；目标 MySQL/Redis 及容量验证待部署后记录 |

## 2026-08-18 系统配置与 SMTP 回归追踪

| 需求 | 实现证据 | 自动化证据 | 当前状态 |
|---|---|---|---|
| 当前配置重置 | `apps/admin/src/lib/operationalSettingsForm.ts`、`SystemSettingsPage.vue` | 响应式快照深复制单元测试；Admin Chromium、Firefox、WebKit 保存后编辑再重置旅程；Staging Chromium 重置 | 已修复 Vue Proxy `DataCloneError`，嵌套导航和用户等级不共享引用；Staging 已验证 |
| SMTP 后台设置可见 | `SystemSettingsPage.vue` 的全量 SMTP 表单 | Admin Chromium、Firefox、WebKit 断言 Host、Port、Password、保存、重置和无发布/回滚控件；Staging Chromium 同项验证 | 本地三浏览器和 Staging 真实页面均通过 |
| 设置页移动端基线 | `admin-authenticated-accessibility.spec.ts` | 当前工作台、运行参数、SMTP 区块与每日配额关键区域 | Chromium 定向可访问性与视觉基线通过；统一门禁通过 |

## 2026-08-18 SEO 设置首阶段需求追踪

| 需求 | 计划代码证据 | 计划自动化证据 | 当前状态 |
|---|---|---|---|
| SEO-01 当前配置直接保存 | `modules/admin/seo_settings.py`、`GET/PUT /admin/settings/seo` | Pydantic 边界、默认值、管理员权限、持久化与审计摘要测试 | 规格已确认；待实现 |
| SEO-02 管理端 SEO 工作台 | `SystemSettingsPage.vue`、`AdminSettingsNavigation.vue`、`services/settings.ts` | Vitest 渲染、校验、保存、重置与错误态测试 | 规格已确认；待实现 |
| SEO-03 公开 SEO 配置 | `modules/site/schemas.py`、`service.py`、`packages/api-contract` | 公开字段白名单、关闭 SEO 降级和秘密字段排除测试 | 规格已确认；待实现 |
| SEO-04 Web 页面元信息 | `apps/web/src/services/seo.ts`、`router/index.ts`、`App.vue` | 路由白名单、title/description/keywords/canonical/OG/robots 单元与浏览器测试 | 规格已确认；待实现 |
| SEO-05 索引安全规则 | 路由 `seoIndexable` 元数据与集中判定 | 认证、账户、私信、通知、发帖、OAuth、搜索和管理页面 `noindex, nofollow` 测试 | 规格已确认；待实现 |
| SEO-06 robots 与 sitemap | 根路径 `/robots.txt`、`/sitemap.xml` | Content-Type、全局禁抓、Sitemap 指令、XML 白名单与敏感路径排除测试 | 规格已确认；待实现 |
| SEO-07 SPA 验收边界 | v3.0 规格 18.22、SEO 实施计划 | 真实浏览器运行后 head 断言；SSR/预渲染单列后续范围 | 边界已确认；不宣称 SSR 收录保证 |
