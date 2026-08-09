# WP3 第 9 次开发迭代：已登录核心页面无障碍与响应式收口

- 日期：2026-08-09
- 工作包：WP3 Web/Admin 端到端与视觉验收
- 范围：已登录 Web 账号安全、隐私中心、Admin 用户治理和角色审批页面的主内容跳转、移动端布局边界、反馈实时语义、Select 可辨识名称和可重复合成会话。

## 交付

- Web/Admin 应用壳新增首个跳过链接 `跳到主要内容`，主内容区统一使用 `id="main-content"` 和 `tabindex="-1"`，支持键盘直接跳转并把焦点落到主内容。
- Web `SecurityPage.vue`、`AccountPrivacyPage.vue` 的错误提示补充 `aria-live="assertive"`；Admin `UserGovernancePage.vue`、`RoleChangesPage.vue` 的加载/操作错误和成功反馈补充 `role` 与实时区语义。
- Admin 用户治理和角色审批的筛选/原因 SelectTrigger 补充显式 `aria-label`；真实 Axe 扫描发现的 `button-name` 严重违规已关闭。
- 新增 `web-authenticated-accessibility.spec.ts`：Web 账号安全 1440 × 900 桌面门禁、隐私中心 390 × 844 移动门禁、跳转主内容键盘断言、页面级无横向溢出、全页 PNG 报告和严重/关键 WCAG 扫描。
- 新增 `admin-authenticated-accessibility.spec.ts`：Admin 用户治理桌面门禁、角色审批移动门禁、跳转主内容键盘断言、响应式布局边界、全页 PNG 报告和严重/关键 WCAG 扫描。
- 增加独立 Web/Admin 合成刷新会话；种子启动时按 family 清理旧轮换链并重建初始会话，避免定向测试消耗令牌后污染全量套件或 CI 重试。Admin 合成会话显式标记 MFA 已验证，不新增生产限流例外。

## 本地验证

- `pnpm typecheck`：workspace 类型检查与 E2E TypeScript 检查通过。
- `pnpm lint`：前端 ESLint、E2E ESLint、前端规范门禁通过，新增违规为 0。
- Admin Vitest：22 个测试文件、52 项测试通过。
- 定向已登录可访问性 E2E：3 项通过；其中 Web 2 项、Admin 1 项，覆盖桌面/移动、键盘跳转、视觉布局和 Axe 严重/关键违规。
- `./scripts/check.ps1 -SkipInstall -IncludeE2E`：统一门禁通过，完整 Playwright Chromium 旅程 28/28 通过；API 测试、迁移往返、前端 lint/typecheck/test/build、桌面端检查和容器配置检查均通过。

## 远端验证

- 功能提交 GitHub Actions `31307983187`：API、Frontend、Desktop、E2E、Container Images 五个作业全部通过。

## 未关闭

- 当前视觉门禁仍是结构化布局和全页报告附件；跨操作系统像素差异批准、人工设计验收和视觉基线存储策略仍待建立。
- Web 贡献、积分信誉、举报申诉、活动记录，以及 Admin 候选审核、信任案件、系统配置和风险告警仍需继续扩展移动端/键盘/屏幕阅读器组合。
- 屏幕阅读器实测、目标环境浏览器矩阵、桌面端实机 E2E、MySQL/Redis 并发与高负载、安全扫描、性能基线、恢复演练和生产验收未关闭。
