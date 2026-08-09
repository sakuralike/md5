# WP3 第 3 次开发迭代：Admin 候选审核与案件原子处置

- 日期：2026-08-09
- 工作包：WP3 Web/Admin 端到端与视觉验收
- 范围：Admin 候选人工审核、举报案件指派/处理/解决、关联候选原子隔离及操作反馈稳定性。

## 交付

- 扩展 `playwright.config.ts` 和 `tests/e2e/support/seed_api.py`，为隔离 SQLite 增加固定 ID 的合成工作流管理员、预启用 TOTP、待验证候选、已验证举报候选和待处理举报案件。
- 新增 `tests/e2e/support/admin_session.ts`，统一使用合成管理员账号和动态 TOTP 登录 Admin，避免依赖首次绑定旅程的共享状态。
- 新增 `tests/e2e/admin-moderation-journeys.spec.ts`，覆盖以下真实浏览器闭环：
  1. 按 SHA-256 定位待验证候选，填写审核说明，人工审核通过并确认不可变状态时间线。
  2. 按案件 ID 定位举报，指派负责人、开始处理、以 `admin.action_taken` 解决案件，并确认关联候选在同一业务处置中从已验证原子进入隔离状态。
- 案件筛选旅程显式等待详情请求完成，避免列表刷新与表单输入之间的异步竞态；测试继续收集并断言浏览器控制台错误。
- 修复 `TrustCasesPage.vue`：管理写操作成功后刷新案件详情时保留成功反馈，避免指派、重开、解决或通知重放的状态提示被 `openCase` 立即清空。
- 管理处置旅程关闭截图与网络 Trace；所有账号、指纹、TOTP 密钥、案件说明和候选密码均为测试专用合成数据，候选密码仅以应用密钥加密后的字段写入种子库。

## 本地验证

- `pnpm e2e --project=admin-chromium tests/e2e/admin-moderation-journeys.spec.ts`：2 项通过。
- `pnpm --filter @password-detective/admin test -- TrustCasesPage.test.ts`：Admin 21 个测试文件、51 项测试通过。
- `pnpm exec eslint playwright.config.ts tests/e2e scripts/e2e apps/admin/src/pages/TrustCasesPage.vue`：通过。
- `pnpm exec tsc -p tsconfig.e2e.json --noEmit`：通过。
- `.\apps\api\.venv\Scripts\ruff.exe check tests/e2e/support/seed_api.py`：通过。
- `.\scripts\check.ps1 -SkipInstall -IncludeE2E`：通过；覆盖 Ruff、API 测试与覆盖率、SQLite 全量迁移往返、前端规范/类型/单测/构建、9 项 Playwright Chromium 旅程和桌面端 Release 构建/测试。
- 远端 GitHub Actions `31294494635`：API、Frontend、Desktop、E2E 和 Container Images 5 个作业全部通过。

## 未关闭

Web 邮箱验证/刷新过期、用户密码/TOTP/会话/隐私操作，Admin 用户治理/角色审批/配置/风险告警的浏览器闭环，视觉快照、移动端溢出、键盘/焦点/错误提示可访问性，以及 Compose/预生产目标环境浏览器验收仍需后续 WP3 轮次完成。
