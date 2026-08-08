# WP2 第 1 次开发迭代：账号申诉与统一案件主体基线

- 日期：2026-08-08
- 分支：`codex/account-appeal-orchestration`
- 范围：账号申诉创建、本人案件详情、统一主体数据模型、共享契约与自动化测试

## 1. 本轮目标

在不复制案件系统的前提下扩展现有 `trust_cases`，让账号申诉复用统一队列、事件、幂等和审计基础。本轮只建立可独立验收的后端纵切，不将既有通用状态转换冒充最终的原子案件处置编排。

## 2. 已实现

### 2.1 数据模型与迁移

- `TrustCaseKind` 新增 `account_appeal`。
- 新增主体类型 `candidate/account/risk_alert`，并通过数据库检查约束保证 `candidate_id`、`target_user_id`、`risk_alert_id` 恰有一个与主体类型匹配。
- 新增 `requested_action` 和 `evidence_summary`；历史候选案件迁移回填为 `candidate` 主体。
- 新增前进迁移 `20260808_0019`，已覆盖升级、降级到上一版本和再次升级。

### 2.2 用户 API

- `POST /api/v1/trust/account-appeals`：目标账号只从登录主体派生，不接受客户端指定；要求 `Idempotency-Key`，每日最多 3 次。
- `GET /api/v1/trust/cases/{case_id}`：只允许提交者读取；其他账号统一返回 404，避免对象枚举。
- 账号申诉使用受控原因码与期望动作；说明和证据摘要各最多 1000 字符并执行首尾空白归一化。
- 创建事件保存请求号；审计只保留结构化主体、原因和动作，不复制说明、证据摘要或处理自由文本。

### 2.3 契约与兼容

- 共享 TypeScript 契约新增账号申诉请求、原因码、恢复动作、主体类型和可空主体引用。
- Web 服务层新增账号申诉创建和本人案件详情调用；现有 Web/Admin 案件列表可正确展示账号、候选和风险告警主体。
- 现有 MFA 管理队列可筛选账号申诉，通用进入复核状态兼容新案件类型。

## 3. 验证范围

- API：创建、幂等重放、幂等冲突、服务端派生本人目标、额外目标字段拒绝、本人详情、跨账号 404、未登录 401、管理队列筛选、进入复核、事件与审计最小披露。
- 迁移：SQLite `upgrade head → downgrade 20260804_0018 → upgrade head`。
- 前端：共享契约类型检查、Web 服务测试、Web/Admin 案件页面既有渲染测试。
- Windows PowerShell 5.1 统一门禁通过：API 94 项通过、1 项真实 Redis 条件测试跳过、覆盖率 90%；共享契约 2 项、Web 23 项、Admin 49 项、Desktop 11 项测试通过。
- Ruff、前端规范检查、类型检查、生产构建、桌面 Release 构建和 SQLite 全量迁移 `upgrade → downgrade base → upgrade` 全部通过。

## 4. 明确未完成

- `/admin/trust-cases/{case_id}/assign`、`resolve`、`reopen` 独立接口及状态/负责人乐观并发。
- 案件结论与账号/候选状态、积分/信誉补偿、通知 Outbox 的单事务编排。
- 案件 SLA、负责人前后值、通知引用和用户/Admin 完整时间线。
- Web 账号申诉表单和本人案件详情页面。
- 锁定或禁用账号的非登录恢复通道；当前规格和接口保持“登录”门禁。

## 5. 下一轮建议

优先冻结指派、处置、重开命令模型及乐观并发字段，再实现 `assign` 与 `reopen`；随后将 `resolve` 与账号/候选副作用、补偿和通知 Outbox 纳入同一事务，并补齐失败回滚测试。
