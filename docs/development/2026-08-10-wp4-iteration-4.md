# WP4 第 4 次开发迭代：认证对象边界与浏览器 Cookie 安全门禁

- 日期：2026-08-10
- 分支：`codex/m5-entry-gates`
- 功能提交：`afba67a`（`test(wp4): add authenticated security probes`）
- 功能提交远端 CI：GitHub Actions `31349411600`，9 个作业全部通过
- 范围：WP4 M5 认证安全动态门禁，不改变现有业务接口语义

## 1. 本轮目标

在上一轮匿名 API DAST 基线之上，补齐两个已认证普通用户的对象级授权边界，以及浏览器刷新 Cookie 的 CSRF/SameSite 动态检查。管理员 MFA/再认证、幂等重放和资源消耗攻击留到下一轮，避免把尚未覆盖的范围误记为完成。

## 2. 实现内容

### 2.1 已认证用户对象边界

- DAST 每次运行创建两个唯一的合成普通用户并分别登录。
- 用户 A 创建隐私导出后，用户 B 读取该导出必须返回 `404 privacy.export_not_found`。
- 用户 A 的会话族由用户 B 撤销必须返回 `404 auth.session_not_found`。
- API 定向测试与黑盒 DAST 同时覆盖，使用唯一后缀和合成密码，不读取或写入开发者账号。

### 2.2 浏览器 Cookie 与来源校验

- 浏览器登录动态解析 `Set-Cookie`，验证刷新 Cookie 的 `HttpOnly`、`SameSite=Lax` 和 `/api/v1/web/auth` 路径隔离。
- 不可信 `Origin` 刷新请求必须返回 `403 request.invalid_origin`。
- 可信 Web 来源携带合成 Cookie 刷新必须成功，证明来源校验没有误伤正常浏览器链路。
- 解析器只将 Cookie 值用于同一探针的后续请求，不把值写入报告；报告只保存检查名称、状态和非敏感结果摘要。

## 3. 验证证据

- 定向 Ruff：通过。
- 定向测试：`12 passed`（DAST 脚本测试与 WP4 API 安全测试）。
- API 全量测试：`123 passed, 1 skipped`；跳过项为真实 Redis 条件测试。
- 本地统一门禁：`./scripts/check.ps1 -SkipInstall -IncludeSecurity` 通过，包含 API、SQLite 迁移往返、前端 lint/typecheck/test/build、桌面 Release 构建、依赖/SAST/SBOM 和 DAST。
- 本地动态 DAST：`10/10` 通过，报告：`.local/security-dast-next/dast-report.json`。
- 本轮保持开发服务可访问：API `8000`、Web `5173`、Admin `5174` 均处于监听状态。

## 4. 未覆盖边界与下一轮入口

本轮不是完整认证渗透测试，也未覆盖管理员对象级越权、管理员 MFA/近期再认证组合、幂等键重放、跨标签刷新竞争、批量资源消耗、长时间并发、OWASP ZAP、目标环境和人工渗透。

下一轮优先实现管理员 MFA/再认证动态滥用矩阵、幂等键重复/冲突重放和资源消耗负向门禁；随后执行 MySQL/Redis/Worker 恢复、性能和可观测性出口。
