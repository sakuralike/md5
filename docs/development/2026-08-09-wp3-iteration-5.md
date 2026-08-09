# WP3 第 5 次开发迭代：Admin 用户治理与角色双人审批闭环

- 日期：2026-08-09
- 工作包：WP3 Web/Admin 端到端与视觉验收
- 范围：普通用户停用/恢复、活跃会话撤销，以及普通角色变更的不同管理员申请与批准。

## 交付

- 扩展 `playwright.config.ts` 与 `tests/e2e/support/seed_api.py`：增加独立复核管理员、用户治理目标、角色变更目标及不可用于登录的合成活跃会话。
- 新增 `tests/e2e/admin-governance-journeys.spec.ts`：
  1. 管理员在一次性再认证、TOTP、结构化原因和幂等门禁下停用普通用户，确认撤销活跃会话，再恢复账号。
  2. 申请管理员创建普通用户到可信贡献者的角色变更请求，由不同复核管理员批准，确认目标会话撤销及角色投影更新。
- 高风险旅程关闭截图和 Trace，不把密码、动态码、再认证令牌或真实个人信息写入测试制品。

## 本地验证

- 定向 Admin E2E：2 项通过。
- `pnpm e2e`：14 项 Chromium 旅程通过。
- ESLint、E2E TypeScript 和种子 Ruff：通过。
- `./scripts/check.ps1 -SkipInstall -IncludeE2E`：统一门禁通过，覆盖 API、SQLite 全量迁移往返、前端 lint/typecheck/test/build、桌面端 Release 检查和 14 项 Chromium 旅程。

## 远端验证

- 待本轮推送后记录 GitHub Actions 运行号。

## 未关闭

系统配置草稿/发布/回滚和风险告警指派/核查/解决浏览器闭环将在 WP3 第 6 轮继续；视觉快照、移动端溢出、键盘/焦点/错误提示可访问性及目标环境验收仍需后续完成。
