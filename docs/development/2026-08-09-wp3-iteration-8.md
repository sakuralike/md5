# WP3 第 8 次开发迭代：视觉、可访问性与刷新竞争收口

- 日期：2026-08-09
- 工作包：WP3 Web/Admin 端到端与视觉验收
- 范围：Web/Admin 首批结构化视觉快照、移动端布局、键盘焦点、错误提示与严重 WCAG 门禁，以及 Web 刷新令牌缺失、过期和并发竞争组合。

## 交付

- 新增 `tests/e2e/support/visual_assertions.ts`，统一检查页面级横向溢出、页面背景、关键区域可见性与布局边界，并将全页 PNG 快照附加到 Playwright 报告；快照只使用公开页面或隔离合成账号，不包含真实凭据和个人信息。
- 新增 `tests/e2e/web-visual-accessibility.spec.ts`：
  1. Web 登录页桌面布局、用户名/密码/TOTP/提交按钮焦点顺序、结构化错误提示与严重/关键 WCAG 违规扫描。
  2. Web 首页 390 × 844 移动视口关键区域、无页面级横向溢出与严重/关键 WCAG 违规扫描。
- 新增 `tests/e2e/admin-visual-accessibility.spec.ts`：
  1. Admin 仪表盘桌面布局、导航和严重/关键 WCAG 违规扫描。
  2. Admin 登录页 390 × 844 移动布局与用户名/密码/TOTP/提交按钮焦点顺序。
- Admin 顶层布局与登录页改为 Shadcn-Vue、Tailwind 语义类和 Mobile-first 响应式结构，补充可访问导航标签、焦点环与错误提示实时区；新增 `App.test.ts` 基础渲染测试。
- 修正 Web 导航、弱化文本、空状态和页脚的语义前景色对比度，使首批页面通过 Axe 严重/关键违规门禁；Web 登录错误提示补充 `role="alert"` 与 `aria-live="assertive"`。
- 扩展 `web-identity-journeys.spec.ts` 与隔离种子，覆盖缺失刷新 Cookie、自然过期，以及两个标签页竞争同一刷新令牌时仅一次轮换成功、竞争请求触发重放检测并撤销令牌族。
- `rotate_refresh_token` 使用条件更新原子认领未撤销会话，关闭并发请求同时轮换同一刷新令牌的竞态；竞争失败分支保持令牌族撤销和不可变审计。
- Admin 候选审核重试逻辑改为以不可变终态事件是否存在决定是否执行处置，避免瞬时可见性判断跳过首次操作。

## 本地验证

- API 身份回归：`apps/api/tests/test_auth.py` 11 项通过。
- Admin Vitest：22 个测试文件、52 项测试通过。
- 定向视觉/身份 E2E：9 项通过。
- `pnpm e2e`：25 项 Chromium 旅程通过。
- API Ruff、前端 ESLint、Admin 类型检查和 E2E TypeScript 检查通过。
- `./scripts/check.ps1 -SkipInstall -IncludeE2E`：统一门禁通过，覆盖 API、SQLite 全量迁移往返、前端 lint/typecheck/test/build、桌面端 Release 检查和 25 项 Chromium 旅程。

## 远端验证

- 功能提交 GitHub Actions `31305403414`：API、Frontend、Desktop、E2E、Container Images 五个作业全部通过。

## 未关闭

- 当前视觉门禁以结构、布局边界、无溢出、全页报告附件和严重/关键 WCAG 违规为稳定基线；跨操作系统像素差异基线与人工批准流程仍待后续建立。
- 仍需扩展 Web 贡献/安全/隐私页面与 Admin 治理/配置/案件页面的移动端、键盘和可访问性组合。
- 屏幕阅读器实测、目标环境浏览器矩阵、桌面端实机 E2E、性能/安全扫描和生产验收未关闭。
