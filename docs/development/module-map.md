# 模块地图

- 更新日期：2026-08-11
- 架构形态：单仓 + FastAPI 模块化单体 + 独立客户端

## 后端模块

| 模块 | 路径 | 当前职责 | 下一步 |
|---|---|---|---|
| Core | `apps/api/src/password_detective/core/` | 配置、令牌、Argon2id、错误、request_id、Redis 限流、数据库幂等、统一通知网关、`notification-webhook-v1` HTTPS/HMAC 签名、浏览器 Cookie、TOTP 秘钥加密、候选秘密保险库、递归日志脱敏 | 生产 KMS 适配器、通知凭据轮换、指标导出与清理任务 |
| Auth | `apps/api/src/password_detective/modules/auth/` | 注册、邮箱验证、密码重置、登录、刷新轮换、重放检测、退出、会话、TOTP 服务、可选身份解析 | M2 个人资料扩展与风险策略 |
| Archives | `apps/api/src/password_detective/modules/archives/` | 完整指纹精确查询、可见性分层、幂等贡献、重复候选合并、揭示配额、证据计数、个人贡献列表和不保存完整指纹的查询遥测 | 高风险揭示二次验证、遥测保留/归档和规模查询优化 |
| Verification | `apps/api/src/password_detective/modules/verification/` | 当前有效反馈、不可变证据历史、`verification-v2` 聚合、Web/桌面证据统一接入、自动状态事件、首次验证结算、自动奖励校正和风险检测接入点 | 跨候选图谱、动态信誉权重和处罚规则 |
| Admin | `apps/api/src/password_detective/modules/admin/` | 独立浏览器登录、RBAC、TOTP/MFA、真实仪表盘、审计中心、用户处置、受控角色变更双人复核，以及不可变配置草稿、差异预览、再认证发布、运行时投影和新版本回滚 | 角色层级配置化、紧急撤权、批量资源上限、审计保留/归档和大规模异步导出 |
| Moderation | `apps/api/src/password_detective/modules/moderation/` | MFA 候选筛选、最小披露详情、证据/状态/奖励校正时间线、`moderation-v1` 人工状态转换、人工首次验证结算、校正汇总、持久化幂等和审计 | 候选合并/删除、案件编排、危险操作再次确认与批量处置资源限制 |
| Community | `apps/api/src/password_detective/modules/community/` | 固定分区、公开主题/回复、邮箱验证与规则确认、纯文本安全展示、用户举报、重复待处理举报阻断、MFA 举报队列、内容移除、主题锁定/置顶/下架/恢复、限流、幂等和审计 | 可配置分区、分区版主授权、标签、关注/点赞、通知、私信和批量治理 |
| Trust Cases | `apps/api/src/password_detective/modules/trust_cases/` | 登录用户举报、贡献者受限申诉、本人账号申诉、本人案件列表/详情、`candidate/account/risk_alert` 单一主体约束、MFA 统一队列/详情、受控状态矩阵、独立指派/重开、案件版本乐观并发、负责人前后事件快照、限流、幂等和审计脱敏 | 原子 `resolve`、结果通知 Outbox、SLA、候选/账号副作用、奖励/信誉补偿、自动分派和用户案件交互收口 |
| Risk Alerts | `apps/api/src/password_detective/modules/risk_alerts/` | `risk-alert-v1` 检测、`risk-alert-sla-v1` 响应/解决时限、MFA 值班人员指派、负责人/超时筛选、不可变事件、事务通知 Outbox、SMTP/Webhook 投递、投递指标/失败队列、幂等人工重放和处置 | 排班与升级链、真实 SMTP 服务商/发件域名验收、最终送达回调、指标导出、动态规则和批量操作；关联分析由 Correlation 模块提供 |
| Reputation | `apps/api/src/password_detective/modules/reputation/` | 本人积分投影、贡献/反馈统计、积分流水、不可变信誉事件、0～100 分投影、`reputation-v1` 幂等奖励和 `reward-compensation-v1` 撤销/恢复校正 | 管理员用户处置、危险操作再次确认和动态风险权重 |
| Correlation | `apps/api/src/password_detective/modules/correlation/` | `correlation-v1` 候选内安装/IP 传递关联组、成功/失败维度动态限权、聚合分析和不可变快照持久化 | 跨候选图谱、通知/SLA、自动处罚与可配置规则 |
| Health | `apps/api/src/password_detective/modules/health/` | 存活、数据库和限流后端就绪检查 | Worker/密钥管理与更细粒度依赖状态 |
| Desktop Verification | `apps/api/src/password_detective/modules/desktop_verification/` | 安装公钥注册/撤销、一次性挑战、版本/时钟/绑定校验、ECDSA 回执验签、防重放与证据接入 | M4 风险评分细化、关联账号分析和人工处置 |
| Desktop Updates | `apps/api/src/password_detective/modules/desktop_updates/` | 稳定/测试通道发布清单、MFA 管理发布、流式制品完整性校验、发布/撤回、匿名版本检查和受控下载 | 对象存储/CDN、正式签名流水线、分批发布与回滚编排 |
| Database | `apps/api/src/password_detective/db/` | 用户、会话、账号动作令牌、幂等、审计、设置、档案、指纹、候选、贡献、积分、信誉事件、奖励校正事件、反馈、证据历史、关联分析快照、自动/人工状态事件、带候选/账号/风险告警单一主体的信任案件及事件、风险告警 SLA/指派，以及通知提供商/回执/失败/重放元数据、社区主题/回复/举报、安装实例、挑战、桌面回执和桌面发布模型 | 案件 SLA、通知引用、负责人前后值和跨候选关联模型 |
| Worker | `apps/api/src/password_detective/worker.py` | Celery 应用、探活、风险告警 SLA 扫描、统一通知网关、签名 Webhook、SMTP STARTTLS/SSL 投递、有限重试和失败终态记录 | SMTP 最终送达/退信回调、投递租约、多渠道路由、独立 Beat、幂等记录清理、验证批处理和报表 |

## 客户端模块

| 模块 | 路径 | 当前职责 | 下一步 |
|---|---|---|---|
| 用户 Web | `apps/web/` | 注册、登录、HttpOnly 刷新会话、本地分块哈希、精确查询、授权贡献、候选揭示、社区验证反馈、社区论坛主题/回复、个人贡献、举报/申诉，以及积分/信誉/反馈历史中心 | Web Worker 隔离、案件结果通知、超大文件性能与浏览器 E2E |
| 管理端 | `apps/admin/` | 独立登录、角色检查、TOTP 登录/首次绑定、真实治理指标仪表盘、审计日志筛选/详情/CSV 导出、候选审核队列/详情/人工处置、用户停用/恢复/会话撤销、配置版本治理、普通角色变更双人审批、举报/申诉队列/详情、风险告警 SLA/负责人/投递指标/失败重放闭环、桌面发布工作台 | 角色事件时间线、紧急撤权、批量处置、案件与候选状态编排和真实通知环境验收 |
| Windows 桌面端 | `apps/desktop-windows/` | ZIP/7z 本地验证、可注入资源限制、合成加密样本矩阵、SHA-256/MD5、DPAPI 安装密钥与令牌、身份重建/重新注册、最低版本提示、挑战和 ECDSA 签名回执、稳定通道自动检查与显式浏览器下载入口 | Windows 10/11 实机 E2E、物理超大样本、静默安装与正式发布签名 |
| Web UI | `packages/web-ui/` | 两个 Vue 应用共享设计令牌、基础样式和 M2 状态样式 | 可访问组件与统一交互状态组件 |
| API Contract | `packages/api-contract/` | 共享认证、浏览器会话、档案查询、贡献、揭示、反馈、管理仪表盘/审计日志/用户治理、候选审核/状态事件/奖励校正、关联组/动态限权摘要、举报/申诉案件、风险告警 SLA/投递指标/失败重放、桌面安装/挑战/回执、社区论坛主题/回复、发布记录和证据快照类型 | 从 OpenAPI 自动生成并做契约差异检查 |

## 前端工程门禁

- 根 `eslint.config.mjs` 统一 Web/Admin 的 Vue 3、TypeScript 严格检查，`src/components/ui/` 保持为 Shadcn-Vue CLI 生成边界。
- `scripts/check-frontend-policy.mjs` 检查业务 `.vue` 的样式块、行内样式、硬编码颜色和原生表单控件；`scripts/frontend-policy-baseline.json` 只冻结存量欠账并阻止新增或基线回退。
- 根 `pnpm lint` 已接入 `scripts/check.ps1` 与 `.github/workflows/ci.yml`；统一检查脚本兼容 Windows PowerShell 5.1 和 PowerShell 7。
- WP1 五轮已完成：App、首页、注册页、Web 举报/申诉与积分/信誉页面，以及 Admin 登录/TOTP、案件处置、风险告警、候选审核和桌面发布页面均已整改；冻结欠账由 11 个文件 164 项清零，新增违规为 0，本地工程出口条件已满足。
## 模块边界规则

1. API 模块不直接导入其他模块的内部仓储；跨模块操作通过公开服务函数或应用编排层完成。Archives 查询只调用 Verification 的公开证据汇总函数。
2. 业务状态改变必须写入领域事件或审计，不在路由中散落状态规则。
3. 候选密码明文只允许在 M2 秘密服务的最小路径出现，不进入日志、异常或前端持久缓存。
4. Web/Admin 只通过 API 契约访问后端；长期刷新令牌仅存在于 HttpOnly Cookie，桌面端使用独立 JSON 令牌流程。
5. Windows 客户端是不可信证据来源，签名回执仍需服务端挑战、防重放和风险规则。
6. 生产与集成环境的限流状态必须由 Redis 共享；关键写操作的幂等结果必须持久化到数据库。
7. 候选秘密加密与去重使用不同用途密钥；生产环境不得直接使用应用主密钥代替 KMS 管理的数据密钥。
8. 桌面升级制品必须经过“声明摘要/大小 → 流式上传校验 → 发布前重校验”的链路；匿名客户端只能访问已发布制品，且更新提示不得自动执行下载内容。

### N2 管理治理安全链

- API：`modules/admin/users.py` 负责对象级保护、乐观并发、状态变更、会话撤销和审计；`modules/auth/reauthentication.py` 提供会话族/目的绑定的一次性凭据。
- Admin：`apps/admin/src/pages/UserGovernancePage.vue` 与 `services/users.ts` 负责确认表单、再认证、幂等键和操作后刷新。
- 配置：`modules/admin/settings.py`、`core/operational_settings.py` 和 `system_setting_versions` 提供固定 Schema 的不可变草稿、差异、发布、投影与回滚。
- Admin：`apps/admin/src/pages/SystemSettingsPage.vue` 提供版本历史、草稿编辑、差异预览和再认证发布/回滚。
- 契约：`packages/api-contract` 共享原因码、再认证、用户治理和配置版本响应类型。
- 角色治理：`modules/admin/role_changes.py`、`apps/admin/src/services/roleChanges.ts`、`apps/admin/src/composables/useRoleChanges.ts` 与 `apps/admin/src/pages/RoleChangesPage.vue` 提供固定普通角色转换、双人复核、分页详情、再认证和凭据清理。
- 下一边界：独立角色事件时间线、紧急撤权、批量资源上限和管理员/服务账号角色治理。

### Community 论坛边界

- 社区模块只承载授权场景下的安全协作文本，不接触候选密码秘密服务，不接收压缩包文件内容。
- 公共 GET 不要求登录；POST 主题/回复通过 `get_current_principal`、邮箱验证、规则确认、Redis/内存限流和 `Idempotency-Key` 保护。
- 本轮仅完成固定分区、主题、回复和锁定状态的产品切片；复杂版主管理、社交关系、私信和商业化能力保持在后续边界。
