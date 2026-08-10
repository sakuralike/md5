# 密码侦探社项目文档

> - 文档基线日期：2026-08-08
> - 唯一维护格式：Markdown（`.md`）

## 当前开发基线

| 文档 | 用途 | 状态 |
|---|---|---|
| [密码侦探社项目规格说明书 v3.0](./密码侦探社项目规格说明书-v3.0.md) | 产品定位、范围、需求、规则、架构、安全与验收标准 | 当前有效 |
| [密码侦探社开发实施计划 v1.0](./密码侦探社开发实施计划-v1.0.md) | 14 周 MVP 计划、任务拆解、里程碑、测试和发布门禁 | 当前有效 |
| [下一步开发方案（2026-08-08）](./密码侦探社下一步开发方案-2026-08-08.md) | 角色审批收口、账号申诉与案件编排、E2E 和 M5 工程准入 | 当前执行 |
| [下一阶段开发计划（2026-08）](./密码侦探社下一阶段开发计划-2026-08.md) | M4 收口、P0 业务闭环和 M5 准入冲刺 | 前序基线 |
| [文档维护规范](./文档维护规范.md) | Markdown 编写、评审、版本和归档规则 | 当前有效 |
| [文档变更记录](./文档变更记录.md) | 记录文档基线的重要变更 | 持续更新 |

## 开发实施记录

- [下一步开发方案（2026-08-08）](./密码侦探社下一步开发方案-2026-08-08.md)
- [WP4 第 16 次开发迭代：证据包封存与审批交接完整性门禁](../docs/development/2026-08-10-wp4-iteration-16.md)
- [WP4 第 15 次开发迭代：Prometheus 与 HA 平台导出接入](../docs/development/2026-08-10-wp4-iteration-15.md)
- [WP4 第 14 次开发迭代：目标环境采集与 HA 事件适配器](../docs/development/2026-08-10-wp4-iteration-14.md)
- [WP4 第 13 次开发迭代：资源趋势与 HA 执行证据合同](../docs/development/2026-08-10-wp4-iteration-13.md)
- [WP4 第 12 次开发迭代：Staging 长时稳定性准入合同](../docs/development/2026-08-10-wp4-iteration-12.md)
- [WP4 第 11 次开发迭代：多实例稳定性与单 Worker 故障收口](../docs/development/2026-08-10-wp4-iteration-11.md)
- [N2 第 12 次开发迭代：WP1 前端规范债务清零与总体验收](../docs/development/2026-08-08-n2-iteration-12.md)
- [N2 第 11 次开发迭代：WP1 Admin 信任案件与风险告警页面整改](../docs/development/2026-08-08-n2-iteration-11.md)
- [N2 第 10 次开发迭代：WP1 Admin 登录与 TOTP 页面整改](../docs/development/2026-08-08-n2-iteration-10.md)
- [N2 第 9 次开发迭代：WP1 用户案件与信誉页面整改](../docs/development/2026-08-08-n2-iteration-9.md)
- [N2 第 8 次开发迭代：WP1 前端质量门禁与用户基础流程首批整改](../docs/development/2026-08-08-n2-iteration-8.md)
- [N2 第 7 次开发迭代：Admin 角色审批工作台收口](../docs/development/2026-08-08-n2-iteration-7.md)
- [当前阶段状态](../docs/development/phase-status.md)
- [N1 第 1 次开发迭代：账号资料、密码与用户 TOTP](../docs/development/2026-08-03-n1-iteration-1.md)
- [N1 第 2 次开发迭代：账号活动与隐私中心](../docs/development/2026-08-03-n1-iteration-2.md)
- [N1 第 3 次开发迭代：认证恢复与 TOTP 登录闭环](../docs/development/2026-08-03-n1-iteration-3.md)
- [下一阶段开发计划（2026-08）](./密码侦探社下一阶段开发计划-2026-08.md)
- [项目整体完成度审计（2026-08-03 复核）](../docs/development/2026-08-03-completion-audit.md)
- [模块地图](../docs/development/module-map.md)
- [M0/M1 第 1 次开发迭代](../docs/development/2026-08-01-m0-m1-iteration-1.md)
- [M4 第 5 次开发迭代：失败激增风险告警](../docs/development/2026-08-02-m4-iteration-5.md)
- [M4 第 4 次开发迭代：奖励补偿与信誉校正](../docs/development/2026-08-02-m4-iteration-4.md)
- [M4 第 3 次开发迭代：积分与信誉中心](../docs/development/2026-08-02-m4-iteration-3.md)
- [M4 第 2 次开发迭代：举报与申诉案件闭环](../docs/development/2026-08-02-m4-iteration-2.md)
- [M4 第 1 次开发迭代：候选人工审核闭环](../docs/development/2026-08-02-m4-iteration-1.md)
- [架构决策记录](../docs/adr/README.md)
- [初始威胁模型](../docs/threat-model/initial-threat-model.md)

## 使用规则

1. 开发、评审和需求变更只修改 Markdown 文件。
2. 若需要 Word 或 PDF，只能从 Markdown 临时导出；导出文件不是事实来源，不回写修改。
3. 原始 Word 文档已移动到 `历史文档/docx归档/`，仅用于追溯。
4. 原始 Word 内容已转换为 `历史文档/原始需求-md/`，但不作为当前开发基线。
5. 原始文档与当前规格冲突时，以《密码侦探社项目规格说明书 v3.0》为准。

## 目录结构

```text
项目文档/
├─ README.md
├─ 密码侦探社项目规格说明书-v3.0.md
├─ 密码侦探社开发实施计划-v1.0.md
├─ 密码侦探社下一步开发方案-2026-08-08.md
├─ 密码侦探社下一阶段开发计划-2026-08.md
├─ 文档维护规范.md
├─ 文档变更记录.md
└─ 历史文档/
   ├─ README.md
   ├─ 原始需求-md/
   ├─ docx归档/
   └─ 工具归档/
```

## 后续建议目录

项目开始开发后，在仓库中逐步增加：

```text
docs/
├─ adr/             # 架构决策记录
├─ api/             # API 契约和示例
├─ runbooks/        # 部署、故障、备份和恢复手册
├─ threat-model/    # 威胁模型与安全评审
├─ testing/         # 测试策略和验收报告
└─ releases/        # 发布说明与回滚记录
```
