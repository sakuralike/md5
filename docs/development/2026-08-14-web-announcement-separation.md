# R3 第 3 轮：桌面公告与 Web 公告独立化

- 日期：2026-08-14
- 状态：实现、专项测试与统一门禁完成；推送和 Staging 部署待回填

## 1. 目标

1. 桌面公告与 Web 公告使用独立数据、API、管理入口和图片资源目录。
2. Web 公告可配置自动关闭秒数，并保持手动关闭按公告修订持久化。
3. 不迁移既有桌面公告，不允许 Web 端回退读取桌面公告。

## 2. 实现

- API：新增 `web_announcements`、Alembic `20260814_0039`、`/api/v1/web/announcements`、`/api/v1/admin/web-announcements` 和 Web 公告图片接口。
- Admin：新增独立“Web 公告”导航、CRUD/发布/归档/图片上传工作区和自动关闭秒数输入。
- Web：公告服务切换为 `/web/announcements`；`null` 不自动关闭，1～86400 秒触发页面内自动隐藏。
- 安全：HTML 继续纯文本化；链接限制 HTTP(S)；自动关闭不写入持久关闭记录。

## 3. 自动化证据

- API 专项：桌面公告与 Web 公告 CRUD、发布、归档、图片、URL/时间窗、渠道隔离和秒数边界。
- Admin：Web 公告 payload、页面渲染、导航计数、lint 与类型检查。
- Web：独立端点、弹窗渲染、自动关闭秒数换算、lint 与类型检查。

## 4. 待回填

- `pwsh ./scripts/check.ps1 -SkipInstall`：通过（Ruff、API、共享契约、Web、Admin、桌面端、构建与迁移往返）。
- Git 提交、远端等价树和 Staging 部署修订。
- Staging `20260814_0039` 迁移、健康检查及桌面/Web 两个公告公开接口的独立冒烟。

## 5. 后续

- 增加真实浏览器假时钟/实时时钟自动关闭旅程。
- 增加已登录 Admin Web 公告创建、发布和归档 E2E。
- 继续桌面 Release 实机、多格式压缩包和正式回滚演练。
