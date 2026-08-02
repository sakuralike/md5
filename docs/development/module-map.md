# 模块地图

- 更新日期：2026-08-02
- 架构形态：单仓 + FastAPI 模块化单体 + 独立客户端

## 后端模块

| 模块 | 路径 | 当前职责 | 下一步 |
|---|---|---|---|
| Core | `apps/api/src/password_detective/core/` | 配置、令牌、Argon2id、错误、request_id、Redis 限流、数据库幂等、通知边界、浏览器 Cookie、TOTP 秘钥加密、候选秘密保险库、递归日志脱敏 | 生产 KMS 适配器、密钥轮换、指标与清理任务 |
| Auth | `apps/api/src/password_detective/modules/auth/` | 注册、邮箱验证、密码重置、登录、刷新轮换、重放检测、退出、会话、TOTP 服务、可选身份解析 | M2 个人资料扩展与风险策略 |
| Archives | `apps/api/src/password_detective/modules/archives/` | 完整指纹精确查询、可见性分层、幂等贡献、重复候选合并、揭示配额、证据计数和个人贡献列表 | 高风险揭示二次验证、规模查询优化 |
| Verification | `apps/api/src/password_detective/modules/verification/` | 当前有效反馈、不可变证据历史、`verification-v1` 聚合、Web/桌面证据统一接入、自动状态事件、首次验证结算、自动奖励校正和风险检测接入点 | M4 关联账号图谱与动态反馈降权 |
| Admin | `apps/api/src/password_detective/modules/admin/` | 独立浏览器登录、RBAC、TOTP 绑定与 MFA 访问门禁 | 举报、配置、危险操作二次确认和审计查询 |
| Moderation | `apps/api/src/password_detective/modules/moderation/` | MFA 候选筛选、最小披露详情、证据/状态/奖励校正时间线、`moderation-v1` 人工状态转换、人工首次验证结算、校正汇总、持久化幂等和审计 | 候选合并/删除、案件编排、危险操作再次确认与批量处置资源限制 |
| Trust Cases | `apps/api/src/password_detective/modules/trust_cases/` | 登录用户举报、贡献者受限申诉、本人案件列表、MFA 统一队列/详情、受控状态矩阵、不可变事件、限流、幂等和审计脱敏 | 结果通知、SLA、候选处置编排、账号申诉和自动分派 |
| Risk Alerts | `apps/api/src/password_detective/modules/risk_alerts/` | `risk-alert-v1` 15 分钟失败激增检测、聚合告警投影、不可变事件、MFA 队列/详情和幂等处置 | 关联账号图谱、通知、SLA、批量操作与动态规则配置 |
| Reputation | `apps/api/src/password_detective/modules/reputation/` | 本人积分投影、贡献/反馈统计、积分流水、不可变信誉事件、0～100 分投影、`reputation-v1` 幂等奖励和 `reward-compensation-v1` 撤销/恢复校正 | 管理员用户处置、危险操作再次确认和动态风险权重 |
| Health | `apps/api/src/password_detective/modules/health/` | 存活、数据库和限流后端就绪检查 | Worker/密钥管理与更细粒度依赖状态 |
| Desktop Verification | `apps/api/src/password_detective/modules/desktop_verification/` | 安装公钥注册/撤销、一次性挑战、版本/时钟/绑定校验、ECDSA 回执验签、防重放与证据接入 | M4 风险评分细化、关联账号分析和人工处置 |
| Desktop Updates | `apps/api/src/password_detective/modules/desktop_updates/` | 稳定/测试通道发布清单、MFA 管理发布、流式制品完整性校验、发布/撤回、匿名版本检查和受控下载 | 对象存储/CDN、正式签名流水线、分批发布与回滚编排 |
| Database | `apps/api/src/password_detective/db/` | 用户、会话、账号动作令牌、幂等、审计、设置、档案、指纹、候选、贡献、积分、信誉事件、奖励校正事件、反馈、证据历史、自动/人工状态事件、信任案件/案件事件、安装实例、挑战、桌面回执和桌面发布模型 | 案件 SLA、通知投递状态和异常关联模型 |
| Worker | `apps/api/src/password_detective/worker.py` | Celery 应用和探活任务 | 邮件投递、幂等记录清理、验证批处理和报表 |

## 客户端模块

| 模块 | 路径 | 当前职责 | 下一步 |
|---|---|---|---|
| 用户 Web | `apps/web/` | 注册、登录、HttpOnly 刷新会话、本地分块哈希、精确查询、授权贡献、候选揭示、社区验证反馈、个人贡献、举报/申诉，以及积分/信誉/反馈历史中心 | Web Worker 隔离、案件结果通知、超大文件性能与浏览器 E2E |
| 管理端 | `apps/admin/` | 独立登录、角色检查、TOTP 登录/首次绑定、候选审核队列/详情/人工处置、状态与奖励校正时间线、举报/申诉队列/详情、桌面发布草稿/上传重试/发布/撤回工作台 | 用户处置、危险操作确认、审计查询、案件与候选状态编排、SLA 和风险指标工作台 |
| Windows 桌面端 | `apps/desktop-windows/` | ZIP/7z 本地验证、可注入资源限制、合成加密样本矩阵、SHA-256/MD5、DPAPI 安装密钥与令牌、身份重建/重新注册、最低版本提示、挑战和 ECDSA 签名回执、稳定通道自动检查与显式浏览器下载入口 | Windows 10/11 实机 E2E、物理超大样本、静默安装与正式发布签名 |
| Web UI | `packages/web-ui/` | 两个 Vue 应用共享设计令牌、基础样式和 M2 状态样式 | 可访问组件与统一交互状态组件 |
| API Contract | `packages/api-contract/` | 共享认证、浏览器会话、档案查询、贡献、揭示、反馈、候选审核/状态事件/奖励校正、举报/申诉案件、桌面安装/挑战/回执、发布记录和证据快照类型 | 从 OpenAPI 自动生成并做契约差异检查 |

## 模块边界规则

1. API 模块不直接导入其他模块的内部仓储；跨模块操作通过公开服务函数或应用编排层完成。Archives 查询只调用 Verification 的公开证据汇总函数。
2. 业务状态改变必须写入领域事件或审计，不在路由中散落状态规则。
3. 候选密码明文只允许在 M2 秘密服务的最小路径出现，不进入日志、异常或前端持久缓存。
4. Web/Admin 只通过 API 契约访问后端；长期刷新令牌仅存在于 HttpOnly Cookie，桌面端使用独立 JSON 令牌流程。
5. Windows 客户端是不可信证据来源，签名回执仍需服务端挑战、防重放和风险规则。
6. 生产与集成环境的限流状态必须由 Redis 共享；关键写操作的幂等结果必须持久化到数据库。
7. 候选秘密加密与去重使用不同用途密钥；生产环境不得直接使用应用主密钥代替 KMS 管理的数据密钥。
8. 桌面升级制品必须经过“声明摘要/大小 → 流式上传校验 → 发布前重校验”的链路；匿名客户端只能访问已发布制品，且更新提示不得自动执行下载内容。
