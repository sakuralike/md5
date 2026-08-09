# WP3 第 2 次开发迭代：Web 查询、揭示、贡献与举报核心旅程

- 日期：2026-08-09
- 工作包：WP3 Web/Admin 端到端与视觉验收
- 范围：合成已验证候选种子、Web 查询/揭示/清除、授权贡献、举报与本人案件时间线。

## 交付

- 扩展 `playwright.config.ts` 的合成配置，提供 Web 旅程账号、已验证 SHA-256/MD5、未匹配 SHA-256 和合成候选密码；所有默认值均为测试专用合成数据。
- 扩展 `tests/e2e/support/seed_api.py`，在隔离 SQLite 中创建普通 Web 用户、归档、SHA-256/MD5 指纹和加密的已验证候选；候选密码只以应用密钥加密后的字段写入种子库。
- 新增 `tests/e2e/web-core-journeys.spec.ts`，覆盖以下真实浏览器闭环：
  1. 查询已验证候选、揭示最高可信密码、确认剩余揭示配额并从页面清除敏感结果。
  2. 查询未匹配指纹、填写授权贡献、提交待验证贡献并确认结果刷新为待验证候选。
  3. 从候选结果进入举报页、提交候选内容举报并确认本人案件时间线出现待处理案件。
- 测试对举报页重复按钮使用表单提交定位，避免“切换到举报模式”和“提交举报”按钮发生严格定位歧义。
- 新增旅程继续使用浏览器控制台错误收集；测试断言不把合成候选密码写入页面清除后的 DOM 或浏览器错误证据。

## 本地验证

- `pnpm e2e --project=web-chromium tests/e2e/web-core-journeys.spec.ts`：3 项通过。
- `.\apps\api\.venv\Scripts\ruff.exe check tests/e2e/support/seed_api.py`：通过。
- `pnpm exec eslint playwright.config.ts tests/e2e scripts/e2e`：通过。
- `node ./scripts/check-frontend-policy.mjs`：通过。
- `pnpm exec tsc -p tsconfig.e2e.json --noEmit`：通过。
- `.\scripts\check.ps1 -SkipInstall -IncludeE2E`：通过；覆盖 Ruff、API 测试与覆盖率、SQLite 全量迁移往返、前端规范/类型/单测/构建、7 项 Playwright Chromium 旅程和桌面端 Release 构建/测试。
- 远端 GitHub Actions `31292352350`：API、Frontend、Desktop、E2E 和 Container Images 5 个作业全部通过。

## 未关闭

Web 邮箱验证/刷新过期、用户安全设置与隐私请求、Admin 候选和案件处置、视觉快照、移动端溢出、键盘/焦点/错误提示可访问性，以及 Compose/预生产目标环境浏览器验收仍需后续 WP3 轮次完成。
