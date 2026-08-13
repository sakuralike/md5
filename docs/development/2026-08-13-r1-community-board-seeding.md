# R1 后端稳定化：社区默认板块并发初始化

日期：2026-08-13

## 本轮目标

关闭社区默认板块在请求并发启动时的唯一约束竞态，保证自动建表测试环境、单实例和多 API 实例均能幂等完成四个默认板块初始化。

## 根因

旧实现先查询 `community_boards.code`，再逐条 `add` 并提交。多个请求或多个 API 进程在首次访问时可能同时读到空结果，随后重复插入相同板块代码，触发 `community_boards.code` 唯一约束异常。生产迁移 `20260812_0032` 已包含确定性种子，但自动建表的集成环境仍需要请求/启动期兜底。

## 已实现

- `apps/api/src/password_detective/modules/community/boards.py` 改为 SQLite `ON CONFLICT DO NOTHING`、MySQL/MariaDB `ON DUPLICATE KEY UPDATE`，其他方言使用保存点和唯一约束兜底。
- 默认板块初始化增加进程内互斥，避免同一 API 进程内重复写入；数据库 upsert 仍承担跨进程幂等。
- `apps/api/src/password_detective/main.py` 在自动建表完成后、服务开始接收请求前执行一次默认板块初始化，降低首次请求竞态窗口。
- 增加 `apps/api/tests/test_community_board_seeding.py`，覆盖两个独立数据库实例的并发初始化，断言最终只有四个默认板块。

## 验证证据

- 定向 Ruff：通过。
- 社区版块、群组、管理端和健康检查测试：12 项通过。
- `pwsh ./scripts/check.ps1 -SkipInstall`：通过；后端测试 189 项通过、1 项跳过，覆盖率 89.52%，前端 lint/typecheck/test/build 通过，迁移往返通过。
- `pnpm e2e`：16/31 通过、15/31 失败；社区移动端主旅程通过，剩余失败属于导航契约、MFA、视觉/无障碍等后续 R1 项，不再出现此前的 `community_boards.code` 并发唯一约束错误。

## Staging 部署证据

- 候选提交：`d5d3800ff825`，远端分支 `codex/m5-entry-gates` 已同步。
- 部署根目录：`/opt/password-detective-staging`；制品 SHA-256：`ad82dbe35839a21cc13adc3622fc1ebda92fc247a94585b942dbe2c6d750fa3e`。
- 运行镜像：`password-detective-api:d5d3800ff825`、`password-detective-web:d5d3800ff825`、`password-detective-admin:d5d3800ff825`；API 2 实例、Worker 3 实例均运行。
- 数据库迁移：MySQL 当前版本 `20260813_0034 (head)`。
- 目标环境冒烟：`GET /api/v1/health/ready` 返回 HTTP 200 且 database/rate_limit 均为 `ok`；Web/Admin 根页面均返回 HTTP 200；`GET /api/v1/community/boards` 返回 4 个默认板块：`general`、`recovery_guides`、`security`、`verification`。
- 部署编排首轮在完成滚动更新后因远端临时脚本 CRLF 尾部解析返回 127；随后已补执行 HA 拓扑启动并复核 API 2、Worker 3、健康检查和 HTTP 冒烟，当前服务状态正常。

## 交付边界

本轮不宣称全量浏览器门禁或生产放行完成；`pnpm e2e` 仍为 16/31 通过、15/31 失败。Staging 部署和短时真实 HTTP 冒烟已完成，后续仍需处理 MFA、导航契约、视觉/无障碍等浏览器门禁。
