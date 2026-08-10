# WP4 第 5 次开发迭代：管理员 MFA、再认证与幂等滥用门禁

- 日期：2026-08-10
- 分支：`codex/m5-entry-gates`
- 本地功能提交：`eb9fa79`（`test(wp4): add privileged abuse probes`）
- 远端等价提交：`4a96db42e49d9857278894d71d7ef367cc82a29c`
- GitHub Actions：`31352246919`，`desktop`、`security-supply-chain`、`api`、`frontend`、`dast-security`、三浏览器 E2E 和 `container-images` 全部通过

## 本轮目标

在上一轮已认证普通用户对象边界和浏览器 Cookie 门禁的基础上，关闭管理员高权限操作的动态滥用缺口：

1. 管理员 MFA 设置、确认和高权限再认证必须形成可重复的负向测试链路。
2. 管理员再认证授权必须短时、一次性消费，并拒绝错误当前密码、过期或重复使用的授权。
3. 管理员状态变更的 `Idempotency-Key` 必须支持精确重放、冲突阻断，避免重复副作用。
4. 再认证失败达到阈值时必须返回标准 `Retry-After`，使客户端可以安全退避。
5. DAST 报告只能保存检查名称、状态和脱敏摘要，不保存密码、TOTP、令牌或 Cookie。

## 实现内容

| 交付项 | 实现位置 | 结果 |
|---|---|---|
| 管理员 MFA/再认证动态探针 | `scripts/dast_security_gate.py` | 每次使用唯一合成管理员，隔离数据库内直接授予管理员角色；覆盖初始 MFA 阻断、TOTP 设置/确认、可信 Origin 登录、再认证成功和错误当前密码拒绝 |
| 管理员高权限入口门禁 | `apps/api/src/password_detective/api/routers/admin.py`、认证/安全核心模块 | 复用既有 MFA、短时再认证和高权限操作约束，不新增绕过业务语义的接口 |
| 幂等精确重放与冲突 | 管理员状态变更、幂等核心及对应测试 | 相同 key 与相同请求返回相同响应；相同 key 改变目标/原因返回 `409 request.idempotency_conflict` |
| 一次性再认证授权 | 管理员状态变更及授权存储 | 已消费授权再次用于其他目标返回 `401 auth.invalid_reauthentication_token` |
| 限流响应头 | `apps/api/src/password_detective/core/errors.py` | `rate_limit.exceeded` 错误同时返回标准 `Retry-After`，保留原结构化错误体 |
| 负向自动化测试 | `apps/api/tests/test_wp4_dast_security.py`、`apps/api/tests/test_m1_security_gates.py` | 覆盖 MFA、错误密码、幂等 replay/conflict、授权重放和限流退避头 |

## 验证证据

- 定向测试：`20 passed, 1 skipped, 1 warning`；跳过项为真实 Redis 条件测试，不影响 SQLite/内存限流的确定性门禁。
- 本地 DAST：`13/13` 通过，报告：`.local/security-dast-wp4-iteration-5b/dast-report.json`。
- DAST 报告 Secret 扫描通过；报告仅包含检查名称、状态和脱敏详情。
- 本地统一门禁：`./scripts/check.ps1 -SkipInstall -IncludeSecurity` 通过，包含 API、前端、桌面、迁移、依赖、SAST、SBOM 和动态安全门禁。
- 远端 CI：运行 `31352246919` 全部成功；本地 Git HTTPS 推送因 GitHub 连接被重置，随后使用已认证 GitHub API 更新远端分支引用，并以远端 CI 复核等价提交内容。

## 本轮关闭与剩余风险

本轮关闭：管理员 MFA 初始阻断与确认、错误当前密码拒绝、短时一次性再认证、幂等精确重放/冲突、再认证授权重放和限流退避响应头的自动化动态证据。

仍未关闭：更完整的管理员对象级越权矩阵、浏览器多标签刷新竞争与重放、认证爬虫/参数模糊测试、批量资源消耗和长时间并发攻击、OWASP ZAP/人工渗透、MySQL/Redis/Worker 恢复、性能、可观测性及预生产/生产环境验收。

## 下一轮入口

进入 WP4 第 6 轮：优先建立 MySQL 备份清空恢复、Redis 限流/会话/任务降级、Worker 中断重启与任务幂等的可重复演练；随后补齐性能基线和指标/告警出口。WP3 的 Edge/Windows、真实 Safari/macOS、NVDA/VoiceOver 和真实移动设备仍按独立外部验收矩阵关闭。
