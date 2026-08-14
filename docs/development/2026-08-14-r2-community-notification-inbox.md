# R2 网页端通知中心实时合并开发记录

- 日期：2026-08-14
- 范围：仅网页端；Windows 桌面端 UI 尚未冻结，本轮不新增桌面功能。
- 对应计划：WP5-I7 通知可靠性第二轮。

## 1. 本轮目标

在第一轮事务 Outbox、Worker/Beat 和 SSE 通道基础上，关闭“全局账户菜单已收到实时未读数，但通知中心仍需手工刷新”的体验缺口，并保证分页快照与实时事件并发时不会丢失新通知。

## 2. 已实现

1. 新增 `community-notifications` Pinia Store，统一保存全局未读数、SSE 连接状态、最新通知和事件修订号。
2. 全局通知流组合函数改用共享 Store；初始快照、ready 事件、实时事件、重连和退出登录均写入同一状态源。
3. 通知中心监听事件修订号，按当前类型筛选实时插入通知，并按 `created_at` 与 ID 稳定倒序排列。
4. 分页和实时事件通过通知 ID 去重；列表请求期间若收到 SSE 事件，响应落地时保留该实时通知，避免旧快照覆盖新事件。
5. 单条已读与全部已读操作同步更新共享未读数，使通知中心和全局账户菜单保持一致。
6. 页面新增连接状态与“实时收到”标识，明确区分快照数据和当前会话新事件。

## 3. 自动化证据

```powershell
pnpm --filter @password-detective/web typecheck
pnpm --filter @password-detective/web lint
pnpm --filter @password-detective/web test -- --run
pnpm --filter @password-detective/web build
pwsh ./scripts/check.ps1 -SkipInstall -IncludeE2E
```

新增 Store 单元测试覆盖通知去重、更新覆盖、稳定倒序、共享未读数和事件修订号；通知中心渲染测试覆盖实时连接状态入口。

## 4. Staging 验收要求

使用两个仅含合成数据的测试用户完成以下真实浏览器链路：

1. 用户 B 登录并打开 `/community/notifications`，页面显示“实时连接正常”。
2. 用户 A 关注用户 B，Worker 从 Outbox 投递通知。
3. 用户 B 无需刷新即可看到关注通知、“实时收到”和递增后的未读数。
4. 用户 B 标记通知已读后，通知中心与全局账户入口的未读状态同步归零。
5. 页面无未处理异常、控制台错误或重复通知。

## 5. 后续范围

- Admin 社区通知 Outbox 失败查询、失败原因展示和受控重放。
- 邮件摘要真实投递、退信/送达证据与目标 SMTP 验收。
- Redis Pub/Sub 或等价广播机制，降低多 API 实例下 SSE 数据库轮询压力。
- 多标签页已读状态同步、连接可观测指标和长连接容量验证。
