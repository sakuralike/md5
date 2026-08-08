# WP2 第 2 次开发迭代：案件指派、重开与乐观并发

- 日期：2026-08-08
- 分支：`codex/trust-case-assignment-reopen`
- 范围：独立案件指派、受控重开、案件版本并发门禁、负责人事件快照、共享契约、Admin 工作台与自动化测试

## 1. 本轮目标

在 WP2 第 1 轮统一案件主体和账号申诉基线之上，先冻结可独立验收的案件命令模型。实现 `assign` 与 `reopen` 的服务端安全边界，并让通用 `transition` 具备一致的版本并发约束；本轮不实现最终原子 `resolve` 或其账号/候选副作用。

## 2. 已实现

### 2.1 数据模型与迁移

- `trust_cases.version` 为非空整数版本号，所有管理写操作按预期版本校验并在成功后递增。
- `trust_case_events` 新增 `previous_assignee_id` 与 `next_assignee_id`，指派、进入复核、重开和其他状态事件可追踪负责人前后快照。
- 新增前进迁移 `20260808_0020`，不修改已应用的 `20260808_0019`；支持升级、降级到上一版本和再次升级。

### 2.2 管理 API 与安全门禁

- `POST /api/v1/admin/trust-cases/{case_id}/assign`：仅允许 `open/in_review` 案件；目标用户必须为启用状态的 `MODERATOR/ADMIN`；要求 MFA、限流、`Idempotency-Key`、受控原因和 `expected_version`。
- `POST /api/v1/admin/trust-cases/{case_id}/reopen`：仅允许 `resolved/dismissed` 案件；使用 `admin.reopened` 受控原因，清理负责人、解决人、结论码、结论说明和解决时间；同样要求 MFA、限流、幂等和 `expected_version`。
- 通用 `transition` 要求 `expected_version`；进入 `in_review` 时保留已有明确负责人，不再把关闭案件重开作为通用状态转换。
- 版本不匹配统一返回 `409 trust.case_version_conflict`，包含当前版本、状态和负责人 ID；审计不复制自由文本。

### 2.3 契约与管理端

- 共享 API 契约新增指派/重开请求和响应类型、原因码、版本及负责人前后字段。
- Admin 案件详情显示案件版本和当前负责人，提供指派与专用重开操作，并统一发送幂等键和预期版本。
- 现有前端规范保持 Shadcn-Vue、Tailwind、严格 TypeScript 和无自定义样式边界。

## 3. 验证范围

- API：指派成功、指派幂等重放、过期版本冲突、进入复核保留负责人、关闭后受控重开、重开幂等重放、非启用指派对象拒绝、事件负责人快照和审计脱敏。
- 前端：Admin 指派/重开服务调用、版本字段和幂等键断言；共享契约、Admin typecheck、lint、测试和构建。
- 统一门禁实测通过：API 97 项（96 通过、1 项真实 Redis 条件测试跳过）、覆盖率 93.07%；共享契约 2 项、Web 23 项、Admin 50 项、Desktop 11 项测试通过；Ruff、前端规范检查、类型检查、生产构建、桌面 Release 构建及 SQLite 全量迁移 `upgrade → downgrade base → upgrade` 通过。

## 4. 明确未完成

- `/admin/trust-cases/{case_id}/resolve` 原子案件处置接口。
- 账号/候选状态副作用、积分/信誉补偿和通知 Outbox 的单事务编排。
- 案件 SLA、自动分派、通知投递状态和 Web 账号申诉表单/用户详情交互。
- 真实 SMTP、浏览器 E2E、目标环境和生产放行验收。

## 5. 下一轮建议

优先实现受控 `resolve` 命令的事务边界和再认证消费语义：按 `account_appeal`、`appeal`、`report` 分支校验允许的结论和副作用，确保案件结论、目标对象状态、奖励/信誉补偿及通知 Outbox 原子提交；随后补充失败回滚、幂等重放、并发冲突和通知不重复发送测试。
