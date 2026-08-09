# WP3 第 7 次开发迭代：Web 邮箱、刷新令牌与移动端键盘门禁

- 日期：2026-08-09
- 工作包：WP3 Web/Admin 端到端与视觉验收
- 范围：Web 邮箱验证一次性消费与重放拒绝、刷新令牌轮换/重放/令牌族撤销，以及邮箱验证页移动视口和键盘操作门禁。

## 交付

- 新增 `tests/e2e/web-identity-journeys.spec.ts`：
  1. 通过隔离的未验证账号确认“待验证”状态，消费一次性邮箱凭证，确认地址栏移除凭证、重复消费被拒绝，并刷新为“已验证”状态。
  2. 通过 HttpOnly Cookie 完成刷新令牌轮换，重放旧令牌后确认整个令牌族被撤销，新访问令牌与轮换后刷新令牌均不可继续使用。
  3. 在 390 × 844 移动视口检查邮箱验证页不存在横向溢出，确认返回登录入口可获得焦点并由 Enter 键激活。
- 扩展 `playwright.config.ts` 与 `tests/e2e/support/seed_api.py`：增加隔离的未验证用户、一次性邮箱凭证和两组可轮换合成刷新会话；数据库只保存凭证摘要，测试制品关闭截图和 Trace。
- 完整套件曾触发生产登录端点每分钟 10 次的真实限流门禁；本轮没有放宽生产限流，而是改用隔离预置刷新会话建立浏览器认证状态，避免跨用例共享来源地址造成伪失败。

## 本地验证

- 定向 Web 身份 E2E：3 项通过。
- `pnpm e2e`：19 项 Chromium 旅程通过。
- E2E ESLint、TypeScript 与种子 Ruff 通过。
- `./scripts/check.ps1 -SkipInstall -IncludeE2E`：统一门禁通过，覆盖 API、SQLite 全量迁移往返、前端 lint/typecheck/test/build、桌面端 Release 检查和 19 项 Chromium 旅程。

## 远端验证

- 待功能提交推送后由 GitHub Actions 验证 API、Frontend、Desktop、E2E 和 Container Images 作业。

## 未关闭

Web/Admin 视觉快照、更多核心页面移动端溢出检查、跨页面键盘/焦点/错误提示可访问性、刷新令牌过期/缺失 Cookie 浏览器组合、目标环境和生产验收仍需后续完成。
