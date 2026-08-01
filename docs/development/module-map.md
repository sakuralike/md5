# 模块地图

- 更新日期：2026-08-01
- 架构形态：单仓 + FastAPI 模块化单体 + 独立客户端

## 后端模块

| 模块 | 路径 | 当前职责 | 下一步 |
|---|---|---|---|
| Core | `apps/api/src/password_detective/core/` | 配置、令牌、Argon2id、错误、request_id、日志、限流/幂等骨架 | Redis 限流、持久化幂等、秘密加密适配器 |
| Auth | `apps/api/src/password_detective/modules/auth/` | 注册、登录、刷新轮换、重放检测、退出、会话管理 | 邮箱验证、密码重置、TOTP、账号风控完善 |
| Admin | `apps/api/src/password_detective/modules/admin/` | RBAC 集成检查 | M4 候选审核、举报、配置和审计查询 |
| Health | `apps/api/src/password_detective/modules/health/` | 存活与数据库就绪检查 | Redis/Worker/密钥管理就绪检查 |
| Database | `apps/api/src/password_detective/db/` | 会话工厂、基础模型、审计写入 | M2 档案/指纹/候选/贡献模型 |
| Worker | `apps/api/src/password_detective/worker.py` | Celery 应用和探活任务 | 邮件、数据清理、批量任务和报表 |

## 客户端模块

| 模块 | 路径 | 当前职责 | 下一步 |
|---|---|---|---|
| 用户 Web | `apps/web/` | 认证、会话安全页、M1 首页 | M2 浏览器分块哈希、查询、贡献、揭示 |
| 管理端 | `apps/admin/` | 独立登录、角色检查、导航骨架 | M4 审核与审计工作台 |
| Windows 桌面端 | `apps/desktop-windows/` | 文件选择、异步 SHA-256/MD5、进度和取消 | M3 ZIP/7z 解压测试、安装密钥、挑战签名 |
| Web UI | `packages/web-ui/` | 两个 Vue 应用共享设计令牌和基础样式 | 可访问组件与状态组件 |
| API Contract | `packages/api-contract/` | 共享认证类型、标准错误和角色判断 | 从 OpenAPI 自动生成并做契约差异检查 |

## 模块边界规则

1. API 模块不直接导入其他模块的内部仓储；跨模块操作通过公开服务函数或应用编排层完成。
2. 业务状态改变必须同时写入领域事件/审计，不在路由中散落状态规则。
3. 候选密码明文只允许在 M2 的秘密服务最小路径出现，不进入日志、异常或前端缓存。
4. Web/Admin 只能通过 API 契约访问后端，不共享数据库语义。
5. Windows 客户端是不可信证据来源，签名回执仍需服务端挑战、防重放和风险规则。
