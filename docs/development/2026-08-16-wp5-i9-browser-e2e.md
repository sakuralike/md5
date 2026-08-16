# 2026-08-16 WP5-I9 私信浏览器验收与统一门禁

## 范围

本轮完成 WP5-I9 异步私信的 Web 真实浏览器主旅程、跨浏览器兼容性、统一门禁和相关回归修复。测试只使用合成账号、合成消息和本地测试密钥，不包含真实密码、令牌、密钥或个人信息。

## 实现与测试变更

- 新增 `tests/e2e/web-community-direct-messages.spec.ts`，串行覆盖发送者、接收者和非成员三类身份。
- Playwright 固件新增三个独立私信账号；发送者和接收者的 `message_policy` 固定为 `everyone`，避免测试依赖默认社交关系。
- E2E API 使用独立的合成私信 AES-GCM 密钥环；Web 浏览器测试通过 Vite `/api/v1` 同源代理访问 API，与生产 Web 反向代理拓扑一致。
- API CORS 允许 `Last-Event-ID`，并新增通知 SSE 预检回归测试，保留独立源部署时的断线游标请求能力。
- Admin 通知 Outbox 增加 `direct_message` 类型的中文标签和筛选项。
- 修复社区搜索 E2E 固件：测试板块的 `minimum_role` 从无效的 `guest` 改为 `UserRole.USER.value`，避免社区首页响应模型校验失败并返回 HTTP 500。

## TDD 与故障定位证据

1. 首次私信旅程因缺少专用 E2E 身份变量失败；补齐发送者、接收者和非成员固件。
2. 会话创建因接收者默认策略为 `following` 返回 HTTP 403；在测试固件中显式设置 `everyone`。
3. WebKit 首次发现通知 SSE 跨域预检拒绝 `Last-Event-ID`；新增失败的 API CORS 测试后补齐允许头。
4. WebKit 在多次登录/退出时仍会把已主动中止的跨源 SSE 记录为 page error；Web E2E 改用生产形态的同源代理，独立 CORS 合同继续由 API 测试覆盖。
5. 首次完整统一门禁中，既有移动端社区旅程发现搜索固件写入无效角色 `guest`，`GET /api/v1/community/home` 返回 HTTP 500；修正枚举值后单项复现测试通过，完整统一门禁复跑通过。

## 浏览器验收

私信旅程覆盖：

- 发送者从公开资料发起或复用一对一会话。
- 页面明确提示“服务端加密存储，不是端到端加密”及仅成员可见边界。
- 发送消息后在收件箱完成归档、恢复、静音和取消静音。
- 接收者看到未读数，打开会话后已读清零并回复。
- 发送者重新登录后可读取回复。
- 非成员访问同一会话得到预期 HTTP 404 和“无权访问该私信会话”，且页面不显示消息正文。
- 浏览器错误观察器未发现非预期 page error 或 console error；非成员 HTTP 404 是被显式断言的安全响应。

结果：

- Chromium：通过。
- Firefox：通过。
- WebKit：通过。
- 定向跨浏览器合计：3/3 通过，耗时约 1.1 分钟。

## 本地验证

```powershell
pnpm lint
pnpm typecheck
pnpm exec playwright test tests/e2e/web-community-direct-messages.spec.ts --project=web-chromium --project=web-firefox --project=web-webkit --workers=1
apps/api/.venv/Scripts/python.exe -m ruff check apps/api/src/password_detective/main.py apps/api/tests/test_cors.py tests/e2e/support/seed_api.py
apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_cors.py apps/api/tests/test_community_direct_messages.py -q
pnpm exec playwright test tests/e2e/web-community-mobile-journeys.spec.ts --project=web-chromium --workers=1
pwsh ./scripts/check.ps1 -SkipInstall -IncludeE2E
```

结果：

- ESLint、前端策略、TypeScript 严格类型检查：通过。
- Ruff：通过。
- CORS 与私信 API 定向测试：11/11 通过。
- 移动端社区回归：1/1 通过。
- 统一门禁：通过；Chromium Web/Admin Playwright 42/42，Windows Desktop 测试 29/29。

## 远端同步

- 本地代码提交：`f7da09ba0b0083241de0ed4dcef383d49da5bfe3`。
- 本地 Git Tree：`265bfdb3d55e424e51c6a500752539fb35b0de56`。
- 常规 HTTPS push 因连接被重置失败后，使用 Git Data API 将同一 Git Tree 写入远端分支；远端等价树提交为 `4c3376e18840fd6b3359811228377c223446d8fa`。
- 远端 ref、提交父链和 Git Tree 已通过 GitHub API 复核；`equivalent_tree=true`。

## Staging 部署与独立复验

- 部署目标：`/opt/password-detective-staging`，部署前生成数据库、源码、`.env` 和 Compose override 备份。
- 迁移：`20260816_0044 (head)`。
- 拓扑：2 个 API、3 个 Worker；Scheduler 与 API/Worker 使用 `password-detective-api:4c3376e18840`，Admin 使用 `password-detective-admin:4c3376e18840`。
- 本轮 Web 运行时代码未变化，保持 `password-detective-web:cf92d1d0e894`，未以无关重建替代发布证据。
- 镜像标签中的 `org.opencontainers.image.source_tree` 与远端 Git Tree `265bfdb3d55e424e51c6a500752539fb35b0de56` 一致。
- HTTP 复核：ready、Web 首页、Admin 首页、私信收件箱和会话 SPA 路由均为 200；未认证私信 API 为 401。
- 通知 SSE 的真实 CORS 预检为 200，响应允许头包含 `Last-Event-ID`；Admin 部署产物包含 `direct_message` 的“私信”标签。
- 独立延时复验再次确认上述迁移、拓扑、镜像和 HTTP 结果；私信密钥环与应用主秘密/候选秘密相互独立，超过 60 秒的 InnoDB 长事务为 0。

## 证据边界

- 本轮已具备本地、远端等价树和 Staging 证据。
- 本轮不宣称 Production 或 UAT 完成；实时 Redis Pub/Sub、消息举报和治理收口仍属于 WP5-I10。
