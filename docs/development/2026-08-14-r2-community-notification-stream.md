# 2026-08-14 R2 社区通知可靠性第一轮

## 范围

本轮只开发网页端通知可靠性；Windows 桌面端 UI 尚未设计冻结，因此不修改桌面端业务或界面。

## 交付清单

- 数据库：`community_notifications.delivery_version`、`community_notification_outbox`、迁移 `20260814_0035_community_notification_outbox.py`。
- 后端：通知创建/聚合刷新写 Outbox；Worker/Beat 调度；偏好、屏蔽、私密群组、主题可见性和下架状态复核。
- API：`GET /api/v1/community/notifications/stream`，支持认证、`Last-Event-ID`、ready/notification 事件、心跳和游标补偿。
- Web：全局账户菜单未读 Badge、连接状态、初始快照校准、断线重连、在线/离线处理和用户级游标隔离。
- 契约与文档：API Contract、API conventions、模块图、需求追踪、后续计划和变更记录同步。

## 验证要求

```powershell
pnpm --filter @password-detective/api-contract build
pnpm --filter @password-detective/web typecheck
pnpm --filter @password-detective/web test -- --run
apps\api\.venv\Scripts\python.exe -m pytest apps/api/tests/test_community.py -q
pwsh ./scripts/check.ps1 -SkipInstall -IncludeE2E
```

目标环境还必须验证迁移 `20260814_0035`、Worker/Scheduler、SSE 公网连接和至少一条真实浏览器未读旅程。邮件摘要真实送达和 Admin Outbox 失败重放不属于本轮出口。
