# 需求—模块—测试追踪矩阵

- 更新日期：2026-08-02

| 需求 | 模块 | 自动化证据 | 状态 |
|---|---|---|---|
| AUTH-01 | `modules/auth` | `apps/api/tests/test_auth.py`、`apps/api/tests/test_m1_security_gates.py`：注册、冲突、邮箱验证、非枚举重发 | M1 完成基础 |
| AUTH-02 | `modules/auth`、`core/browser_session` | `apps/api/tests/test_auth.py`、`apps/api/tests/test_m1_security_gates.py`：登录、轮换、摘要存储、重放、HttpOnly Cookie | M1 完成 |
| AUTH-03 | `modules/auth` | `apps/api/tests/test_auth.py`、`apps/api/tests/test_m1_security_gates.py`：会话列表、撤销、密码重置撤销、无访问令牌浏览器登出 | M1 完成 |
| AUTH-04 | `modules/auth/totp`、`modules/admin` | `apps/api/tests/test_m1_security_gates.py`：TOTP 绑定、密文存储、登录验证、MFA 声明、管理门禁 | M1 管理员基础完成；高风险动作二次验证在 M4 细化 |
| AUTH-05 | `core/rate_limit` | `apps/api/tests/test_security.py`、`apps/api/tests/test_m1_security_gates.py`：端点限流、跨实例 FakeRedis、真实 Redis 双客户端门禁 | M1 分布式基础与本地真实 Redis 门禁完成 |
| AUTH-06 | `core/security` | `apps/api/tests/test_auth.py`：Argon2id 哈希、错误密码拒绝 | M1 完成 |
| 关键写幂等 | `core/idempotency`、`modules/archives`、`modules/verification` | `apps/api/tests/test_m1_security_gates.py`、`apps/api/tests/test_m2_archive_core.py`、`apps/api/tests/test_m2_verification.py`：缓存响应、请求冲突、密码重置、贡献与反馈接入 | M1/M2 首版完成 |
| HASH-01～04 | `apps/web/src/services/fingerprint.ts`、`HomePage.vue` | `apps/web/src/services/fingerprint.test.ts`：SHA-256/MD5 分块、取消、进度、完整指纹格式识别 | M2 首版完成；Web Worker、超大文件性能和浏览器 E2E 待实施 |
| SEARCH-01～06 | `modules/archives` | `apps/api/tests/test_m2_archive_core.py`：完整指纹精确匹配、匿名/登录可见性、仅 verified 揭示、每日配额和审计 | M2 首版完成；已验证种子浏览器 E2E 与规模压测待实施 |
| SUB-01～06 | `modules/archives`、`modules/verification`、`core/candidate_secrets` | `apps/api/tests/test_m2_archive_core.py`、`apps/api/tests/test_m2_verification.py`、`apps/api/tests/test_security.py`：授权声明、持久化幂等、重复合并、密文与 HMAC、待结算及首次 verified 结算 | M2 核心完成；文件名元数据细化和更复杂风控留后续 |
| VERIFY-01～07 | `modules/verification` | `apps/api/tests/test_m2_verification.py`：单账号唯一有效反馈、不可变历史、关联键去重、双成功验证、三失败隔离、verified 降级、状态事件、规则版本和积分幂等 | M2 Web 反馈与自动状态基础完成；M3 桌面签名回执、防重放，M4 关联账号/短时异常/人工审核待实现 |
| DESK-01～08 | `apps/desktop-windows`、`modules/desktop_verification` | `apps/desktop-windows.tests/DesktopSecurityTests.cs`、`apps/desktop-windows.tests/ArchiveVerificationMatrixTests.cs`、`apps/api/tests/test_m3_desktop_verification.py`：DPAPI 身份持久化/重建、ECDSA DER 签名、规范载荷、加密 ZIP/7z 正确与错误密码、损坏/不支持格式、受控内容读取、资源限制、取消、路径穿越、最低版本详情、签名篡改、过期/重放、账号切换、撤销、时钟偏差和双独立回执 | M3 自动化核心与恢复 UX 完成；8 GiB 物理样本和 Windows 10/11 实机 E2E 待外部验收 |
| DESK-09～13 | `modules/desktop_updates`、`apps/admin`、`apps/desktop-windows` | `apps/api/tests/test_m3_desktop_updates.py`、`apps/admin/src/services/desktopReleases.test.ts`、`apps/desktop-windows.tests/DesktopUpdateClientTests.cs`：版本/目标选择、声明大小与摘要、原始制品上传、发布/撤回、生产签名元数据门禁、管理端元数据规范化与上传恢复、匿名检查、下载完整性、客户端查询参数和清单解析 | M3 后端发布通道、管理端发布闭环与显式升级入口完成；正式 Authenticode 流水线、分批发布和静默安装留后续 |
| 管理端需求 | `modules/admin`、`modules/desktop_updates`、`apps/admin` | `apps/api/tests/test_auth.py`、`apps/api/tests/test_m1_security_gates.py`、`apps/admin/src/services/desktopReleases.test.ts`：RBAC、普通用户拒绝、TOTP/MFA、发布元数据与原始制品上传 | M1 安全入口与 M3 桌面发布工作台完成，M4 审核/处置业务待实现 |
| 前端认证传输 | Web/Admin API Client | `apps/web/src/services/api.test.ts`、`apps/admin/src/services/api.test.ts` | M1 基础完成 |
| 敏感数据日志保护 | `core/logging` | `apps/api/tests/test_security.py`：嵌套字典/列表敏感字段递归脱敏 | M2 首版完成 |

真实 Redis 测试在普通单元测试中默认跳过；本地 Docker 双客户端门禁已通过，CI 仍通过 `RUN_REDIS_INTEGRATION=1` 和 Redis 服务显式启用。Docker 空环境已通过；生产 KMS 和托管分支保护仍属于外部环境验收，不以单元测试替代。
