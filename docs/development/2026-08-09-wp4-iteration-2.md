# WP4 第 2 次开发迭代：镜像、Secret 与限期风险豁免门禁

- 日期：2026-08-09
- 分支：`codex/m5-entry-gates`
- 功能提交：`0ef12ee`、`07abd25`
- 远端验证：GitHub Actions `31331945963`

## 1. 本轮目标

1. 对 API、Web、Admin 三个最终容器镜像执行高危和严重漏洞扫描。
2. 对已提交仓库内容执行 Secret 扫描，不扫描本地 `.env`、缓存和构建目录。
3. 建立可校验、可到期、双人批准的风险接受登记；未登记结果默认阻断。
4. 保留扫描 JSON、判定摘要和 SHA-256 清单，并绑定到提交 SHA。
5. 启动本地 API、Web 和 Admin，确认浏览器入口及前端代理可访问。

## 2. 实现内容

### 2.1 扫描与阻断

- `container-images` 作业在构建后加载三个镜像，使用固定提交 SHA 的 Trivy Action 和明确的 Trivy `v0.73.0` 扫描。
- 三个镜像报告分别使用 `image:api`、`image:web`、`image:admin` 作用域；仓库 Secret 报告使用 `repo:secrets` 作用域。
- `verify_release_security.py` 只允许高危/严重结果由同作用域、同 Finding ID、同严重级别且未过期的登记覆盖。
- 风险负责人不得同时作为批准人；登记必须包含工单、原因和未来到期日期。
- CI 上传 `release-security-evidence-<commit-sha>`，包含四份 Trivy JSON、判定摘要和 `RELEASE_SHA256SUMS`。

### 2.2 首批镜像整改

首次远端运行 `31331415752` 正确阻断旧基础镜像中的历史系统包漏洞，仓库 Secret 结果为 0。未通过新增豁免绕过，而是完成以下整改：

- API：`python:3.12-slim` 更新为 `python:3.12.13-alpine3.23`，构建时执行 `apk upgrade --no-cache`。
- Web/Admin 构建层：更新为 `node:22.23.1-alpine3.23`。
- Web/Admin 运行层：`nginx:1.27-alpine` 更新为 `nginx:1.30.4-alpine3.24`，构建时执行 `apk upgrade --no-cache`。

整改后的远端运行 `31331945963` 中，三个最终镜像高危/严重漏洞均为 0，仓库 Secret 为 0，风险接受登记为 0。

## 3. 验证结果

### 3.1 本地自动化

```powershell
pwsh ./scripts/security-gate.ps1
pwsh ./scripts/check.ps1 -SkipInstall -IncludeSecurity
```

结果：

- 发布安全校验器与既有安全产物校验器共 9 项单元测试通过。
- API、迁移往返、前端 lint/typecheck/test/build、Desktop Release 构建与测试通过。
- Python/Node 依赖审计、API Bandit、SBOM 与风险登记有效期检查通过。
- 使用校验过 SHA-256 的 Trivy `v0.73.0` Windows 制品执行本地仓库 Secret 扫描，结果为 0。
- 本机 Docker Desktop 客户端存在，但 Linux 引擎未运行，因此未将本机环境冒充为镜像实扫证据；镜像构建与扫描由远端 Linux CI 完成。

### 3.2 远端自动化

GitHub Actions `31331945963` 八个作业全部成功：

- `api`
- `frontend`
- `security-supply-chain`
- `desktop`
- `container-images`
- `e2e (chromium)`
- `e2e (firefox)`
- `e2e (webkit)`

下载 `release-security-evidence-07abd2566fd4bfaeb973bd0a24274856a83aa636` 后，再次在本地执行发布安全校验器，四份报告均通过，摘要为：

- `finding_count = 0`
- `accepted_count = 0`
- `blocking_count = 0`
- `risk_acceptance_count = 0`

## 4. 本地访问验证

本轮结束时已启动并验证：

- API：`http://127.0.0.1:8000/api/v1/health/ready`
- Web：`http://localhost:5173/`
- Admin：`http://localhost:5174/`
- Web/Admin `/api` 代理健康检查均返回 HTTP 200。

这些是当前工作站的开发进程，不是 Compose、预生产或生产部署证据。

## 5. 未关闭边界

- DAST、对象级越权、CSRF/XSS、重放和资源消耗专项安全测试。
- 前端源码 SAST、正式秘密管理平台及提交前钩子。
- MySQL/Redis/Worker 恢复演练和 RPO/RTO 实测。
- 性能基线、指标出口、监控告警平台和目标 Compose 完整回归。
- 风险接受审批目前只校验静态登记结构；正式组织审批系统和审计签字仍未接入。
