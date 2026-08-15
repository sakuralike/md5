# 2026-08-15 Web 公告真实浏览器验收

## 范围

本轮只覆盖 Web 公告渠道，不修改桌面公告数据、接口或资源目录。测试数据均为本地/测试环境合成公告，不包含真实密码、令牌或个人信息。

## 实现变更

- `tests/e2e/support/web_announcements.ts`：通过测试管理会话创建并发布合成 Web 公告。
- `tests/e2e/admin-web-announcements.spec.ts`：验证已登录 Admin 的草稿创建、自动关闭秒数、发布和状态反馈。
- `tests/e2e/web-announcements.spec.ts`：验证自动关闭、手动关闭、`localStorage` 持久化和公开接口数据。
- `apps/admin/src/pages/WebAnnouncementsPage.vue`：保留保存/发布/归档后的成功反馈，避免重新加载选中记录时清空提示。

## 验证命令与结果

```powershell
pnpm exec tsc -p tsconfig.e2e.json --noEmit
pnpm exec eslint tests/e2e/support/web_announcements.ts tests/e2e/admin-web-announcements.spec.ts tests/e2e/web-announcements.spec.ts
pnpm --filter @password-detective/admin typecheck
pnpm exec playwright test tests/e2e/web-announcements.spec.ts --project=web-chromium
pnpm exec playwright test tests/e2e/admin-web-announcements.spec.ts --project=admin-chromium
```

结果：

- E2E TypeScript：通过。
- 新增 E2E 文件 ESLint：通过。
- Admin typecheck：通过。
- Web Chromium：2/2 通过。
- Admin Chromium：1/1 通过。
- 浏览器错误观察器未发现未处理 page error 或 console error。

## 未覆盖项

- Firefox/WebKit 的同等浏览器旅程尚未完成。
- 桌面端 Release 包仍需目标 Windows 实机回归。
- 正式环境回滚演练仍需单独执行。