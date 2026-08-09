# WP3 第 4 次开发迭代：Web 用户安全与隐私浏览器闭环

- 日期：2026-08-09
- 工作包：WP3 Web/Admin 端到端与视觉验收
- 范围：Web 密码修改、会话撤销、TOTP 启停与登录门禁、隐私用途确认、个人数据一次性导出、账号删除请求创建与撤销。

## 交付

- 扩展 `playwright.config.ts` 与 `tests/e2e/support/seed_api.py`：增加三个隔离的合成 Web 用户和两个预置的非当前安全会话。
- 新增 `tests/e2e/web-account-security-journeys.spec.ts`，覆盖以下真实 FastAPI/Vite/Chromium 闭环：
  1. 展示多个登录会话、撤销其他会话，修改密码后确认剩余非当前会话全部撤销。
  2. 生成 TOTP 配置、动态码确认启用、无动态码登录被拒、带动态码登录成功，再通过再认证停用 TOTP。
  3. 确认“个人数据导出”授权声明，申请并一次性下载 JSON 导出文件，创建账号删除请求后在撤销期内取消。
- 测试使用固定合成账号和隔离 SQLite；密码、下载令牌和 TOTP 密钥不写入截图或 Trace。预置会话只写入不可用于登录的合成刷新哈希，浏览器仍通过真实登录 API 获取当前会话。
- 保持生产 `auth.login` 速率限制不变；通过数据库种子会话减少重复登录，避免测试套件以无界重试掩盖限流问题。

## 本地验证

- `pnpm e2e --project=web-chromium tests/e2e/web-account-security-journeys.spec.ts`：3 项通过。
- `pnpm e2e --project=admin-chromium tests/e2e/admin-moderation-journeys.spec.ts`：2 项通过，并复核跨测试案件种子可重复。
- `pnpm e2e`：12 项 Chromium 旅程通过。
- `pnpm exec eslint playwright.config.ts tests/e2e scripts/e2e`：通过。
- `pnpm exec tsc -p tsconfig.e2e.json --noEmit`：通过。
- `./apps/api/.venv/Scripts/ruff.exe check tests/e2e/support/seed_api.py`：通过。
- `./scripts/check.ps1 -SkipInstall -IncludeE2E`：统一门禁通过，覆盖 API、SQLite 全量迁移往返、前端 lint/typecheck/test/build、桌面端 Release 检查和 12 项 Chromium 旅程。

## 远端验证

- GitHub Actions `31296867172`：API、Frontend、Desktop、E2E、Container Images 五个作业全部通过。

## 未关闭

Web 邮箱验证/刷新过期、复制与过期会话组合旅程，Admin 用户治理/角色审批/配置/风险告警浏览器闭环，视觉快照、移动端溢出、键盘/焦点/错误提示可访问性，以及 Compose/预生产目标环境浏览器验收仍需后续 WP3 轮次完成。
