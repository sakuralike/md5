# WP5-I3 第 5 个开发切片：移动端社区主旅程

- 日期：2026-08-12
- 范围：社区首页、发帖、详情、回复和返回首页的移动端 Playwright 主旅程
- 非范围：真实目标环境部署/MySQL 回归、提及通知、点赞/收藏、真机设备兼容性

## 实现

1. 新增 `tests/e2e/web-community-mobile-journeys.spec.ts`。
2. 用例使用 Chromium `web-chromium` 项目，并固定为 390×844、触控、移动模式。
3. 用例以已验证的合成 E2E 用户通过真实登录页登录，进入 `/community`。
4. 用例从首页点击“发布新主题”，填写合成主题与正文、确认社区规则并发布，确认路由进入独立详情页。
5. 用例在详情页发布合成回复，确认回复正文、公开回复数说明和返回首页后的主题摘要均可见。
6. 用例接入 `observeBrowserErrors` / `expectNoBrowserErrors`，避免仅以 DOM 文本断言掩盖浏览器运行错误。

## 安全与数据边界

- E2E 只使用配置中的合成用户和测试文本；不输入真实密码、令牌、密钥或个人信息。
- 主题与回复仍由现有邮箱验证、规则确认、幂等键、限流和服务端校验约束。
- 测试不输出访问令牌、刷新 Cookie、数据库连接字符串或用户秘密。

## 自动化覆盖

- 登录后的移动端社区首页与发布入口。
- 独立发布页的主题/正文长度条件及规则确认。
- 发布后到独立详情页的跳转。
- 验证后发布回复及 `1 条回复，支持两级定向回复。` 的计数说明。
- 从详情页返回首页后看到刚发布的主题。
- 整个旅程的浏览器错误观测。

## 验证结果

- 专项 E2E：`pnpm exec playwright test tests/e2e/web-community-mobile-journeys.spec.ts --project=web-chromium` 通过（1 passed）。
- 统一门禁：`pwsh ./scripts/check.ps1 -SkipInstall` 通过，覆盖后端 Ruff/pytest/90% 总覆盖率、Alembic 前滚-降级-前滚、脚本专项检查、前端 ESLint/typecheck/Vitest/build。

## 结论

移动端社区主旅程的本地 Chromium 证据已补齐。WP5-I3 仍不能声明整体完成：真实目标环境（含 MySQL）回归和提及通知仍是后续工作，且本地移动视口不替代 iOS Safari、Android 真机或生产验收。
