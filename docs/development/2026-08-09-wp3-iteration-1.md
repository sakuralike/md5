# WP3 第 1 次开发迭代：Playwright 基础设施与认证核心旅程

- 日期：2026-08-09
- 工作包：WP3 Web/Admin 端到端与视觉验收
- 范围：隔离浏览器测试环境、Web 认证核心旅程、Admin 首次 TOTP 绑定与二次登录、CI 门禁。

## 交付

- 根目录引入 Playwright Chromium，统一提供 `pnpm e2e`、`pnpm e2e:install` 和 HTML 报告命令。
- `scripts/e2e/start-api.mjs` 每轮清理独立 SQLite 数据库，使用内存限流和内存通知网关，并由 `seed_api.py` 写入合成管理员；不依赖开发者本地数据库。
- Web E2E 覆盖游客路由门禁、注册、自动登录、退出和重新登录。
- Admin E2E 覆盖游客路由门禁、首次登录强制 TOTP 绑定、动态码确认和启用 MFA 后二次登录。
- 修复 Admin TOTP 手工密钥向 Shadcn-Vue Input 传递 `value` 而非 `model-value`，导致真实浏览器中输入框属性有值但 DOM value 为空的问题。
- 认证场景关闭截图和网络 Trace，并在读取后立即遮蔽 TOTP 密钥；无凭据游客场景保留失败 Trace，避免认证制品记录密码、访问令牌或 TOTP 密钥。
- GitHub Actions 新增独立 `e2e` 作业，安装 API、Chromium 和前端依赖后运行真实浏览器测试；失败时仅上传 `.local/playwright` 短期证据。
- 首次远端运行同时暴露并修复 `20260808_0019`～`0022` 的 MySQL 回滚顺序问题：先移除外键再删除依赖索引，整表回滚则直接删表并原子清理约束与索引。

## 本地验证

- `pnpm lint`
- `pnpm typecheck`
- `pnpm e2e`：Web/Admin 共 4 项通过
- E2E 使用 `127.0.0.1:18100` API、`15173` Web 和 `15174` Admin，数据库位于被 Git 忽略的 `.local/playwright/`。

## 未关闭

本轮只建立认证与路由门禁基线。查询/揭示/贡献、账号安全、举报申诉、Admin 处置、视觉快照、移动端、可访问性和目标环境浏览器验收仍需后续 WP3 轮次完成。
