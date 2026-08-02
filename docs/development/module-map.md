# 模块地图

- 更新日期：2026-08-02
- 架构形态：单仓 + FastAPI 模块化单体 + 独立客户端

## 后端模块

| 模块 | 路径 | 当前职责 | 下一步 |
|---|---|---|---|
| Core | `apps/api/src/password_detective/core/` | 配置、令牌、Argon2id、错误、request_id、Redis 限流、数据库幂等、通知边界、浏览器 Cookie、TOTP 秘钥加密 | 候选秘密加密适配器、指标与清理任务 |
| Auth | `apps/api/src/password_detective/modules/auth/` | 注册、邮箱验证、密码重置、登录、刷新轮换、重放检测、退出、会话、TOTP 服务 | M2 个人资料扩展与风险策略 |
| Admin | `apps/api/src/password_detective/modules/admin/` | 独立浏览器登录、RBAC、TOTP 绑定与 MFA 访问门禁 | M4 候选审核、举报、配置和审计查询 |
| Health | `apps/api/src/password_detective/modules/health/` | 存活、数据库和限流后端就绪检查 | Worker/密钥管理与更细粒度依赖状态 |
| Database | `apps/api/src/password_detective/db/` | 用户、会话、账号动作令牌、幂等、审计、设置模型 | M2 档案/指纹/候选/贡献模型 |
| Worker | `apps/api/src/password_detective/worker.py` | Celery 应用和探活任务 | 邮件投递、幂等记录清理、批量任务和报表 |

## 客户端模块

| 模块 | 路径 | 当前职责 | 下一步 |
|---|---|---|---|
| 用户 Web | `apps/web/` | 注册、登录、HttpOnly 刷新会话、会话安全页、M1 首页 | M2 浏览器分块哈希、查询、贡献、揭示 |
| 管理端 | `apps/admin/` | 独立登录、角色检查、TOTP 登录/首次绑定、导航骨架 | M4 审核与审计工作台 |
| Windows 桌面端 | `apps/desktop-windows/` | 文件选择、异步 SHA-256/MD5、进度和取消 | M3 ZIP/7z 解压测试、安装密钥、挑战签名 |
| Web UI | `packages/web-ui/` | 两个 Vue 应用共享设计令牌和基础样式 | 可访问组件与状态组件 |
| API Contract | `packages/api-contract/` | 共享认证、浏览器会话、用户/会话、标准错误和角色类型 | 从 OpenAPI 自动生成并做契约差异检查 |

## 模块边界规则

1. API 模块不直接导入其他模块的内部仓储；跨模块操作通过公开服务函数或应用编排层完成。
2. 业务状态改变必须写入领域事件或审计，不在路由中散落状态规则。
3. 候选密码明文只允许在 M2 秘密服务的最小路径出现，不进入日志、异常或前端缓存。
4. Web/Admin 只通过 API 契约访问后端；长期刷新令牌仅存在于 HttpOnly Cookie，桌面端使用独立 JSON 令牌流程。
5. Windows 客户端是不可信证据来源，签名回执仍需服务端挑战、防重放和风险规则。
6. 生产与集成环境的限流状态必须由 Redis 共享；关键写操作的幂等结果必须持久化到数据库。
