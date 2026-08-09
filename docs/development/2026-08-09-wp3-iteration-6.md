# WP3 第 6 次开发迭代：系统配置与风险告警浏览器闭环

- 日期：2026-08-09
- 工作包：WP3 Web/Admin 端到端与视觉验收
- 范围：系统配置不可变草稿、发布、历史版本回滚，以及风险告警指派、核查和解决。

## 交付

- 新增 `tests/e2e/admin-operations-journeys.spec.ts`：
  1. 管理员创建并发布两个系统配置版本，选择已被取代的历史版本，并通过管理员 MFA 与一次性再认证创建新的不可变回滚版本。
  2. 管理员打开隔离合成风险告警，将其指派给具备 MFA 的值班管理员，完成开始核查和确认处置，并核对不可变告警时间线。
- 扩展 `playwright.config.ts` 与 `tests/e2e/support/seed_api.py`：增加隔离的高风险候选、失败证据和待响应风险告警投影；全部使用合成标识和加密候选字段。
- 修复 `SystemSettingsPage.vue` 和 `RiskAlertsPage.vue` 在成功写操作后刷新详情时立即清空成功提示的问题，使配置草稿/发布/回滚和告警指派/处置都能保留明确反馈。
- 配置再认证旅程关闭截图和 Trace，不把密码、TOTP、再认证令牌或真实个人信息写入测试制品。

## 本地验证

- 定向 Admin E2E：2 项通过。
- `pnpm e2e`：16 项 Chromium 旅程通过。
- Admin ESLint、TypeScript 和 51 项 Vitest 通过；E2E ESLint、TypeScript 与种子 Ruff 通过。
- `./scripts/check.ps1 -SkipInstall -IncludeE2E`：统一门禁通过，覆盖 API、SQLite 全量迁移往返、前端 lint/typecheck/test/build、桌面端 Release 检查和 16 项 Chromium 旅程。

## 远端验证

- 待本轮推送后记录 GitHub Actions 运行号。

## 未关闭

Web 邮箱验证与刷新令牌异常组合、视觉快照、移动端溢出、键盘/焦点/错误提示可访问性、目标环境和生产验收仍需后续完成。
