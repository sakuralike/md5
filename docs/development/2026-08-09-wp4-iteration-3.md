# WP4 第 3 次开发迭代：API 动态安全与负向门禁

- 日期：2026-08-09
- 分支：`codex/m5-entry-gates`
- 功能提交：`58c218c`、`45af0d3`
- 远端验证：GitHub Actions `31340260242`

## 1. 本轮目标

1. 建立不依赖当前开发数据的隔离 API 动态安全门禁。
2. 固化 API 安全响应头、CORS 拒绝、匿名授权边界和错误最小披露。
3. 阻断超大 JSON 请求体，并覆盖分块传输绕过。
4. 将 DAST 报告、API 日志和提交 SHA 绑定到远端 CI 制品。
5. 保持本地 API、Web、Admin 开发入口可访问。

## 2. 实现内容

### 2.1 HTTP 安全中间件

新增 `HttpSecurityMiddleware`：

- 对 `/api/` 响应统一增加 `nosniff`、禁止 iframe、最小 Referrer、受限 Permissions Policy 和 JSON CSP。
- 除业务显式缓存响应外，默认使用 `Cache-Control: no-store`。
- `MAX_JSON_BODY_BYTES` 默认 `1 MiB`，同时处理声明长度和分块请求实际字节；超过限制返回结构化 `413`。
- 保持桌面二进制制品上传的独立流式上限，不用 JSON 上限覆盖大文件策略。

### 2.2 负向安全测试

新增 7 项 API 测试，覆盖：

- 正常、鉴权失败和方法错误响应的安全头。
- 可信与非可信 CORS 预检。
- `Content-Length` 与分块超限。
- XSS、密码和令牌合成标记不反射。
- 匿名访问本人隐私资源和管理端资源时统一拒绝。

### 2.3 动态探针与 CI

- `scripts/dast_security_gate.py` 执行 8 项黑盒检查并输出结构化 JSON。
- `scripts/dast-security-gate.ps1` 使用端口 `8011`、隔离 SQLite 和合成密钥启动/停止专用 API。
- `pnpm security:dast` 提供统一入口；`check.ps1 -IncludeSecurity` 同时执行静态和动态安全门禁。
- CI 新增 `dast-security` 作业，并上传 `dast-security-evidence-<commit-sha>`。

## 3. 验证结果

### 3.1 本地统一门禁

```powershell
./scripts/check.ps1 -SkipInstall -IncludeSecurity
```

结果：

- API Ruff 通过；109 项通过、1 项真实 Redis 条件测试跳过，覆盖率 90.20%。
- SQLite Alembic `upgrade → downgrade base → upgrade` 通过。
- 前端 lint、typecheck、Vitest 和生产构建通过。
- Desktop Release 构建与测试通过。
- 11 项安全脚本单元测试通过；依赖审计、Bandit、SBOM 和发布策略通过。
- 隔离动态探针 8/8 通过。

### 3.2 远端自动化

首次运行 `31339839339` 中，新增 DAST 作业本身通过；Linux Ruff 正确发现 Python 脚本带 shebang 但 Git 未设置可执行位，导致供应链作业失败。移除无必要 shebang 后，提交 `45af0d3` 的运行 `31340260242` 全部 9 个作业通过：

- `api`
- `frontend`
- `security-supply-chain`
- `dast-security`
- `desktop`
- `container-images`
- `e2e (chromium)`
- `e2e (firefox)`
- `e2e (webkit)`

下载远端 DAST 制品后复核：`total=8`、`passed=8`、`failed=0`。

## 4. 本地访问边界

开发服务继续使用：

- API：`http://127.0.0.1:8000/api/v1/health/ready`
- Web：`http://localhost:5173/`
- Admin：`http://localhost:5174/`

DAST 使用独立端口 `8011`，运行结束后自动停止，不影响上述开发进程。

## 5. 未关闭边界

- 当前是确定性匿名 API DAST 基线，不是完整认证爬虫或人工渗透。
- 已认证用户之间的 BOLA、管理员 MFA/再认证、幂等和重放动态矩阵仍待补齐。
- 浏览器 Cookie CSRF/SameSite、参数模糊测试、批量资源消耗和长时并发攻击未关闭。
- 恢复、性能、指标出口、目标 Compose 与生产环境安全评估仍是后续 WP4 工作。
