# 本地开发指南

## 前置条件

- Python 3.12+
- Node.js 22 与 pnpm 11
- .NET 10 SDK（Windows 桌面端）
- Docker Desktop（容器联调和空环境门禁需要）

## API

```powershell
./scripts/setup-api.ps1
./scripts/dev-api.ps1
```

默认开发数据库为 `apps/api/.local/password-detective.db`，桌面升级制品目录为仓库根目录 `.local/desktop-updates`，默认限流后端为内存。该组合只用于本机单进程开发；集成和生产环境必须使用 MySQL、Redis 与持久化制品存储。

若要本地连接 Redis：

```powershell
$env:RATE_LIMIT_BACKEND = "redis"
$env:REDIS_URL = "redis://localhost:6379/0"
./scripts/dev-api.ps1
```

账号验证、密码重置和风险告警通知默认使用内存通知网关。容器环境默认使用不输出邮箱和令牌的日志占位网关；需要联调提供商适配器时可启用签名 Webhook：

```powershell
$env:NOTIFICATION_BACKEND = "webhook"
$env:NOTIFICATION_WEBHOOK_URL = "https://notifications.synthetic.example.com/deliveries"
$env:NOTIFICATION_WEBHOOK_SECRET = "replace-with-at-least-32-random-characters"
$env:NOTIFICATION_WEBHOOK_TIMEOUT_SECONDS = "10"
./scripts/dev-api.ps1
```

Webhook 仅允许 HTTPS，并使用 `notification-webhook-v1` 规范 JSON、UTC 时间戳和 HMAC-SHA256 签名。示例地址和密钥均为合成占位符；不得把真实令牌或密钥写入项目文档、提交或日志。真实 staging/production 端点、凭据轮换、网络白名单和数据处理协议仍需单独验收。

需要通过标准 SMTP 发送账户令牌和风险告警邮件时：

```powershell
$env:NOTIFICATION_BACKEND = "smtp"
$env:NOTIFICATION_SMTP_HOST = "smtp.synthetic.example.com"
$env:NOTIFICATION_SMTP_PORT = "587"
$env:NOTIFICATION_SMTP_SECURITY = "starttls"
$env:NOTIFICATION_SMTP_USERNAME = "synthetic-user"
$env:NOTIFICATION_SMTP_PASSWORD = "replace-with-provider-app-password"
$env:NOTIFICATION_SMTP_SENDER_EMAIL = "no-reply@synthetic.example.com"
$env:NOTIFICATION_SMTP_SENDER_NAME = "密码侦探社"
$env:NOTIFICATION_SMTP_TIMEOUT_SECONDS = "10"
./scripts/dev-api.ps1
```

`starttls` 是默认生产模式，`ssl` 用于隐式 TLS，`none` 仅允许本地和测试环境。非本地环境必须同时配置用户名、密码和加密模式。SMTP 密码不得写入仓库；生产环境应从秘密管理系统注入。SMTP 接受后保存的 Message-ID 不是最终送达证明，发件域名、SPF、DKIM、DMARC、配额和退信链路仍需在选定服务商环境验收。

M2 候选秘密和揭示策略可通过以下变量配置：

```powershell
$env:CANDIDATE_SECRET_KEY_VERSION = "v1"
$env:DAILY_REVEAL_QUOTA = "5"
$env:SUBMISSION_PENDING_POINTS = "1"
$env:VERIFICATION_REWARD_POINTS = "1"
```

验证状态规则当前固定为 `verification-v2`，关联分析规则固定为 `correlation-v1`；规则版本会写入反馈历史、关联聚合快照和状态事件。修改阈值或关联策略时必须发布新规则版本并补充迁移/回放测试，不能直接改写历史证据。

本地/测试适配器使用 `APP_SECRET_KEY` 按用途派生候选加密密钥和 HMAC 去重密钥，仅用于开发闭环。生产部署必须接入独立 KMS/密钥管理适配器，并完成密钥版本轮换演练。

## Web 与 Admin

```powershell
pnpm install
pnpm dev:web
pnpm dev:admin
```

默认地址分别为 `http://localhost:5173` 和 `http://localhost:5174`。Web 本地指纹计算建议上限由 `VITE_MAX_ARCHIVE_SIZE_BYTES` 控制，默认 20 GiB；仍采用分块读取，不一次性载入内存。两者使用独立 HttpOnly 刷新 Cookie；如果更换端口或域名，必须同步更新 `CORS_ORIGINS`。生产环境必须设置 `BROWSER_COOKIE_SECURE=true` 并使用 HTTPS。

### Playwright 浏览器门禁

首次使用时安装项目锁定版本的浏览器：

```powershell
pnpm e2e:install
```

各命令会独立重建合成 SQLite 和测试账号，不要在同一 Playwright 进程中直接运行全部六个项目：

```powershell
pnpm e2e                 # Chromium 30 项
pnpm e2e:firefox        # Firefox 30 项
pnpm e2e:webkit         # WebKit 30 项
pnpm e2e:cross-browser  # 依次执行三个隔离浏览器，共 90 项
```

完整统一门禁可使用：

```powershell
./scripts/check.ps1 -SkipInstall -IncludeCrossBrowserE2E
```

无头 WebKit 不能注入 Safari 的系统“完整键盘访问”偏好，因此自动化仅验证跳过链接可聚焦和可由 Enter 激活；macOS Safari 的首次 Tab 可达性、VoiceOver 和真实设备行为必须按浏览器矩阵人工执行。

## Windows Desktop

```powershell
dotnet run --project ./apps/desktop-windows/PasswordDetective.Desktop.csproj
dotnet test ./apps/desktop-windows.tests/PasswordDetective.Desktop.Tests.csproj -c Release
```

默认 API 地址为 `http://localhost:8000/api/v1/`。安装身份保存于当前用户 `%LocalAppData%/PasswordDetective/installation-identity.json`，其中私钥由 DPAPI 保护；桌面访问/刷新令牌保存在同目录的 DPAPI 密文文件中。候选密码、压缩包内容和目录不会写入这些文件。

加密压缩包测试样本必须由项目脚本使用合成数据生成，不手工提交来源不明的压缩包：

```powershell
python -m venv ./.local/desktop-fixtures-venv
& ./.local/desktop-fixtures-venv/Scripts/python.exe -m pip install -r ./scripts/desktop-fixtures-requirements.txt
& ./.local/desktop-fixtures-venv/Scripts/python.exe ./scripts/generate-desktop-archive-fixtures.py
```

样本说明和固定合成密码见 [`apps/desktop-windows.tests/Fixtures/README.md`](../../apps/desktop-windows.tests/Fixtures/README.md)。服务端返回安装撤销、绑定冲突或密钥不一致时，客户端会启用新身份生成/重新注册操作；最低版本拒绝只显示升级提示，不应通过更换身份绕过。

桌面端启动后会匿名请求 `stable/windows` 更新清单，并按当前进程架构选择 `x64` 或 `arm64`。发现更新时只展示发布信息和“打开升级下载”按钮；按钮通过系统浏览器访问后端下载入口，不静默下载或执行安装包。

### 本地发布合成升级制品

以下变量控制制品目录、大小上限和下载缓存：

```powershell
$env:DESKTOP_UPDATE_STORAGE_PATH = ".local/desktop-updates"
$env:DESKTOP_UPDATE_MAX_ARTIFACT_BYTES = "536870912"
$env:DESKTOP_UPDATE_DOWNLOAD_CACHE_SECONDS = "86400"
```

优先使用管理端的“桌面发布”页面完成本地操作：

```powershell
pnpm dev:admin
```

1. 使用已启用 TOTP 的合成管理员账号登录 `http://127.0.0.1:5174`。
2. 从受控构建输出选择 `.msix`、`.msixbundle` 或 `.exe`，并使用 `Get-FileHash -Algorithm SHA256` 获取摘要。
3. 创建草稿并上传；网络中断时可在“草稿制品重试”区域重新选择同名、同大小文件。
4. 复核通道、架构、版本、最低版本、摘要和签名记录后显式发布；需要停止分发时执行撤回。

管理端浏览器只做输入格式、文件名和大小的前置校验，不会宣称已经完成 Authenticode 验签。制品摘要由后端在上传、发布和下载前重新校验。

也可以直接调用 API。管理员访问令牌必须来自已完成 TOTP 验证的会话。示例令牌与制品均为本地合成值，不要把真实令牌写入脚本或文档：

```powershell
$artifact = Join-Path $PWD ".local/synthetic-update.msix"
[IO.File]::WriteAllBytes($artifact, [Text.Encoding]::UTF8.GetBytes("synthetic desktop artifact"))
$sha256 = (Get-FileHash $artifact -Algorithm SHA256).Hash.ToLowerInvariant()
$headers = @{ Authorization = "Bearer $env:SYNTHETIC_ADMIN_MFA_TOKEN" }

$release = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/admin/desktop-releases" `
  -Headers $headers `
  -ContentType "application/json" `
  -Body (@{
    channel = "stable"
    platform = "windows"
    architecture = "x64"
    version = "1.0.1"
    minimum_supported_version = "1.0.0"
    mandatory = $false
    release_notes = "合成发布说明"
    artifact_filename = "synthetic-update.msix"
    artifact_sha256 = $sha256
    artifact_size_bytes = (Get-Item $artifact).Length
    content_type = "application/octet-stream"
    code_signature_status = "test_signed"
  } | ConvertTo-Json)

Invoke-RestMethod `
  -Method Put `
  -Uri "http://127.0.0.1:8000/api/v1/admin/desktop-releases/$($release.id)/artifact" `
  -Headers $headers `
  -ContentType "application/octet-stream" `
  -InFile $artifact

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/admin/desktop-releases/$($release.id)/publish" `
  -Headers $headers
```

开发环境允许发布 `unsigned`/`test_signed` 制品；`APP_ENV=production` 时只有发布记录标记为 `verified` 且包含签名者与证书指纹才能发布。该门禁是发布流程声明，不替代 Authenticode 实际验证；生产流水线仍必须独立核验签名。

## 安全与供应链门禁

安装安全工具后，可独立运行生产依赖审计、API SAST 和 API CycloneDX SBOM：

```powershell
$env:PYTHONUTF8 = "1"
./apps/api/.venv/Scripts/python.exe -m pip install -e ".\apps\api[dev,security]"
pnpm install --frozen-lockfile
pnpm security:audit
```

证据默认写入 `.local/security/`。也可以通过 `./scripts/check.ps1 -SkipInstall -IncludeSecurity` 将安全门禁并入统一检查。远端 CI 额外生成仓库级 CycloneDX SBOM，并以提交 SHA 命名上传证据。详细规则见[安全与供应链门禁](../security/supply-chain-gates.md)。

动态 API 基线使用隔离数据库和非默认端口，不会操作当前开发服务：

```powershell
pnpm security:dast
```

报告默认写入 `.local/security-dast/dast-report.json`。当前 DAST 固定执行 13 项检查，除匿名与普通用户对象边界、浏览器刷新 Cookie 安全外，还包含隔离数据库内唯一合成管理员的 MFA/再认证、幂等精确重放/冲突、一次性授权重放拒绝和限流 `Retry-After` 校验；管理员角色通过白盒测试 fixture 授予，不新增生产 bootstrap 接口。报告不保存密码、TOTP、令牌或 Cookie 值。`check.ps1 -IncludeSecurity` 会同时运行静态门禁和动态门禁；远端 `dast-security` 作业上传提交级报告与 API 日志。规则、检查项和未覆盖边界见 [API 动态安全基线](../security/dast-baseline.md)。

## 恢复演练

恢复门禁使用独立 Compose 项目和 `18120/13316/16379` 端口，不会占用默认的本地 API、MySQL 和 Redis 端口，但会清理该专用项目的数据卷：

```powershell
pnpm recovery:drill
python ./scripts/verify_recovery_evidence.py `
  --report ./.local/recovery-wp4-iteration-6/recovery-report.json `
  --write-checksums
```

也可显式并入统一门禁：

```powershell
./scripts/check.ps1 -SkipInstall -IncludeRecovery
```

脚本验证 MySQL 备份/清空/恢复、Redis 故障期间 liveness/readiness 和限流 fail-closed、Worker 中断重启与隐私导出任务幂等。默认结束后销毁专用环境；详细参数、RPO/RTO 阈值和失败处理见[WP4 恢复演练运行手册](../runbooks/wp4-recovery-drill.md)。

## 统一检查

```powershell
./scripts/check.ps1
```

已有依赖时可跳过安装：

```powershell
./scripts/check.ps1 -SkipInstall
```

脚本默认执行 Ruff、pytest 覆盖率、SQLite Alembic 往返、TypeScript、Vitest、生产构建、WPF Release 构建和桌面安全测试；`-IncludeSecurity` 和 `-IncludeRecovery` 分别显式增加安全与恢复门禁。托管 CI 还会启动 MySQL 8.4，执行一次完整的 Alembic `upgrade → downgrade base → upgrade` 往返，避免 SQLite 无法暴露的数据库方言兼容问题。

## Docker 空环境门禁

```powershell
Copy-Item .env.example .env
# 将 APP_SECRET_KEY 改为仅用于本地验收的随机值
./scripts/smoke-compose.ps1
```

执行前先确认 `docker version` 同时显示 Client 和 Server；仅安装 Docker CLI 而 Docker Desktop/WSL 2 引擎未就绪时不能通过该门禁。

脚本会删除本项目 Compose 卷、重新构建并等待服务就绪，然后用合成账号完成注册和登录，并检查 Web/Admin HTTP 响应。若项目路径包含中文等非 ASCII 字符，脚本会自动分配临时 ASCII 盘符以兼容 Docker BuildKit，并在结束时释放。默认结束后清理环境；调试时可使用 `-KeepEnvironment`。此脚本会清除当前 Compose 项目的数据库和 Redis 数据，不应用于含有需要保留数据的环境。

## 发布镜像与 Secret 门禁

只验证限期风险接受登记的结构、双人批准和有效期：

```powershell
pnpm security:release-policy
```

完整 CI 会构建并加载 API、Web、Admin 三个最终镜像，执行 HIGH/CRITICAL 漏洞扫描和仓库 Secret 扫描，再由仓库校验器统一应用 `security/risk-acceptances.json`。本地拥有可运行的 Docker 引擎和 Trivy 时，可以按 [发布镜像、Secret 与风险接受门禁](../security/release-security-gates.md) 复现；引擎不可用时，不得用策略单测替代镜像实扫证据。

2026-08-09 首批远端通过证据为 GitHub Actions `31331945963`：三个镜像高危/严重漏洞 0、仓库 Secret 0、风险接受 0。

## 安全要求

1. `.env` 不进入版本库。
2. 测试账号、邮箱和候选密码必须是合成数据。
3. 不在日志中记录请求体、密码、Authorization、Cookie、TOTP 秘钥或一次性令牌；动态探针只能使用合成标记。
4. 本地 SQLite 不复制到集成或生产环境。
5. 不用内存限流器替代集成/生产 Redis 验收。
6. 候选秘密不得进入浏览器持久存储、日志、审计详情或异常文本；揭示响应不得被缓存。
7. 桌面制品目录和安装包不得提交 Git；生产下载必须使用 HTTPS，且只有发布流水线可以把签名状态标记为 `verified`。
8. JSON 请求体默认上限为 1 MiB；如需调整 `MAX_JSON_BODY_BYTES`，必须保留字段级限制和资源消耗测试，二进制桌面制品继续使用独立流式上限。
