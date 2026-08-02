# 需求—模块—测试追踪矩阵

- 更新日期：2026-08-02

| 需求 | 模块 | 自动化证据 | 状态 |
|---|---|---|---|
| AUTH-01 | `modules/auth` | `apps/api/tests/test_auth.py`、`apps/api/tests/test_m1_security_gates.py`：注册、冲突、邮箱验证、非枚举重发 | M1 完成基础 |
| AUTH-02 | `modules/auth`、`core/browser_session` | `apps/api/tests/test_auth.py`、`apps/api/tests/test_m1_security_gates.py`：登录、轮换、摘要存储、重放、HttpOnly Cookie | M1 完成 |
| AUTH-03 | `modules/auth` | `apps/api/tests/test_auth.py`、`apps/api/tests/test_m1_security_gates.py`：会话列表、撤销、密码重置撤销、无访问令牌浏览器登出 | M1 完成 |
| AUTH-04 | `modules/auth/totp`、`modules/admin` | `apps/api/tests/test_m1_security_gates.py`：TOTP 绑定、密文存储、登录验证、MFA 声明、管理门禁 | M1 管理员基础完成；高风险动作二次验证在 M4 细化 |
| AUTH-05 | `core/rate_limit` | `apps/api/tests/test_security.py`、`apps/api/tests/test_m1_security_gates.py`：端点限流、跨实例 FakeRedis、可选真实 Redis | M1 分布式基础完成；真实 Redis 环境门禁待执行 |
| AUTH-06 | `core/security` | `apps/api/tests/test_auth.py`：Argon2id 哈希、错误密码拒绝 | M1 完成 |
| 关键写幂等 | `core/idempotency`、`modules/archives` | `apps/api/tests/test_m1_security_gates.py`、`apps/api/tests/test_m2_archive_core.py`：缓存响应、请求冲突、密码重置与贡献接入 | M1/M2 首版完成 |
| HASH-01～04 | `apps/web/src/services/fingerprint.ts`、`HomePage.vue` | `apps/web/src/services/fingerprint.test.ts`：SHA-256/MD5 分块、取消、进度、完整指纹格式识别 | M2 首版完成；Web Worker、超大文件性能和浏览器 E2E 待实施 |
| SEARCH-01～06 | `modules/archives` | `apps/api/tests/test_m2_archive_core.py`：完整指纹精确匹配、匿名/登录可见性、仅 verified 揭示、每日配额和审计 | M2 首版完成；已验证种子浏览器 E2E 与规模压测待实施 |
| SUB-01～06 | `modules/archives`、`core/candidate_secrets` | `apps/api/tests/test_m2_archive_core.py`、`apps/api/tests/test_security.py`：授权声明、持久化幂等、重复候选合并、密文存储、独立 HMAC 去重、待结算积分 | M2 核心首版完成；文件元数据、正式积分结算和风控规则待细化 |
| VERIFY-01～07 | `modules/verification` | 待新增：独立证据、重放、隔离和状态时间线 | M2 第 2 次迭代及 M3/M4 待实现 |
| 管理端需求 | `modules/admin` | `apps/api/tests/test_auth.py`、`apps/api/tests/test_m1_security_gates.py`：RBAC、普通用户拒绝、TOTP/MFA | M1 入口完成，M4 业务功能待实现 |
| 前端认证传输 | Web/Admin API Client | `apps/web/src/services/api.test.ts`、`apps/admin/src/services/api.test.ts` | M1 基础完成 |
| 敏感数据日志保护 | `core/logging` | `apps/api/tests/test_security.py`：嵌套字典/列表敏感字段递归脱敏 | M2 首版完成 |

真实 Redis 测试默认跳过；CI 通过 `RUN_REDIS_INTEGRATION=1` 和 Redis 服务显式启用。Docker 空环境、生产 KMS 和托管分支保护属于环境验收，不以单元测试替代。
