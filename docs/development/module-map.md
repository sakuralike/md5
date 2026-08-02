# 模块地图

- 更新日期：2026-08-02
- 架构形态：单仓 + FastAPI 模块化单体 + 独立客户端

## 后端模块

| 模块 | 路径 | 当前职责 | 下一步 |
|---|---|---|---|
| Core | `apps/api/src/password_detective/core/` | 配置、令牌、Argon2id、错误、request_id、Redis 限流、数据库幂等、通知边界、浏览器 Cookie、TOTP 秘钥加密、候选秘密保险库、递归日志脱敏 | 生产 KMS 适配器、密钥轮换、指标与清理任务 |
| Auth | `apps/api/src/password_detective/modules/auth/` | 注册、邮箱验证、密码重置、登录、刷新轮换、重放检测、退出、会话、TOTP 服务、可选身份解析 | M2 个人资料扩展与风险策略 |
| Archives | `apps/api/src/password_detective/modules/archives/` | 完整指纹精确查询、可见性分层、幂等贡献、重复候选合并、揭示配额、证据计数和个人贡献列表 | 高风险揭示二次验证、规模查询优化 |
| Verification | `apps/api/src/password_detective/modules/verification/` | 当前有效反馈、不可变证据历史、`verification-v1` 聚合、Web/桌面证据统一接入、自动状态事件和首次验证积分结算 | M4 关联账号、短时异常和人工审核 |
| Admin | `apps/api/src/password_detective/modules/admin/` | 独立浏览器登录、RBAC、TOTP 绑定与 MFA 访问门禁 | M4 候选审核、举报、配置和审计查询 |
| Health | `apps/api/src/password_detective/modules/health/` | 存活、数据库和限流后端就绪检查 | Worker/密钥管理与更细粒度依赖状态 |
| Desktop Verification | `apps/api/src/password_detective/modules/desktop_verification/` | 安装公钥注册/撤销、一次性挑战、版本/时钟/绑定校验、ECDSA 回执验签、防重放与证据接入 | M4 风险评分细化、关联账号分析和人工处置 |
| Database | `apps/api/src/password_detective/db/` | 用户、会话、账号动作令牌、幂等、审计、设置、档案、指纹、候选、贡献、积分、反馈、证据历史、状态事件、安装实例、挑战和桌面回执模型 | 举报与信誉事件 |
| Worker | `apps/api/src/password_detective/worker.py` | Celery 应用和探活任务 | 邮件投递、幂等记录清理、验证批处理和报表 |

## 客户端模块

| 模块 | 路径 | 当前职责 | 下一步 |
|---|---|---|---|
| 用户 Web | `apps/web/` | 注册、登录、HttpOnly 刷新会话、本地分块哈希、精确查询、授权贡献、候选揭示、社区验证反馈和个人贡献 | Web Worker 隔离、反馈历史页、超大文件性能与浏览器 E2E |
| 管理端 | `apps/admin/` | 独立登录、角色检查、TOTP 登录/首次绑定、导航骨架 | M4 审核与审计工作台 |
| Windows 桌面端 | `apps/desktop-windows/` | ZIP/7z 本地验证、资源限制、SHA-256/MD5、DPAPI 安装密钥与令牌、登录、公钥注册、挑战和 ECDSA 签名回执 | 代表性加密 7z 样本矩阵、安装撤销后的重新注册 UX、自动更新与发布签名 |
| Web UI | `packages/web-ui/` | 两个 Vue 应用共享设计令牌、基础样式和 M2 状态样式 | 可访问组件与统一交互状态组件 |
| API Contract | `packages/api-contract/` | 共享认证、浏览器会话、档案查询、贡献、揭示、反馈、桌面安装/挑战/回执和证据快照类型 | 从 OpenAPI 自动生成并做契约差异检查 |

## 模块边界规则

1. API 模块不直接导入其他模块的内部仓储；跨模块操作通过公开服务函数或应用编排层完成。Archives 查询只调用 Verification 的公开证据汇总函数。
2. 业务状态改变必须写入领域事件或审计，不在路由中散落状态规则。
3. 候选密码明文只允许在 M2 秘密服务的最小路径出现，不进入日志、异常或前端持久缓存。
4. Web/Admin 只通过 API 契约访问后端；长期刷新令牌仅存在于 HttpOnly Cookie，桌面端使用独立 JSON 令牌流程。
5. Windows 客户端是不可信证据来源，签名回执仍需服务端挑战、防重放和风险规则。
6. 生产与集成环境的限流状态必须由 Redis 共享；关键写操作的幂等结果必须持久化到数据库。
7. 候选秘密加密与去重使用不同用途密钥；生产环境不得直接使用应用主密钥代替 KMS 管理的数据密钥。
