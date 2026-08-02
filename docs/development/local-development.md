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

账号验证和密码重置默认使用内存通知网关。容器环境使用不输出邮箱和令牌的日志占位网关；接入正式邮件提供商前，不应将其视为真实投递。

M2 候选秘密和揭示策略可通过以下变量配置：

```powershell
$env:CANDIDATE_SECRET_KEY_VERSION = "v1"
$env:DAILY_REVEAL_QUOTA = "5"
$env:SUBMISSION_PENDING_POINTS = "1"
$env:VERIFICATION_REWARD_POINTS = "1"
```

验证状态规则当前固定为 `verification-v1`；规则版本会写入反馈历史和状态事件。修改阈值时必须发布新规则版本并补充迁移/回放测试，不能直接改写历史证据。

本地/测试适配器使用 `APP_SECRET_KEY` 按用途派生候选加密密钥和 HMAC 去重密钥，仅用于开发闭环。生产部署必须接入独立 KMS/密钥管理适配器，并完成密钥版本轮换演练。

## Web 与 Admin

```powershell
pnpm install
pnpm dev:web
pnpm dev:admin
```

默认地址分别为 `http://localhost:5173` 和 `http://localhost:5174`。Web 本地指纹计算建议上限由 `VITE_MAX_ARCHIVE_SIZE_BYTES` 控制，默认 20 GiB；仍采用分块读取，不一次性载入内存。两者使用独立 HttpOnly 刷新 Cookie；如果更换端口或域名，必须同步更新 `CORS_ORIGINS`。生产环境必须设置 `BROWSER_COOKIE_SECURE=true` 并使用 HTTPS。

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

## 统一检查

```powershell
./scripts/check.ps1
```

已有依赖时可跳过安装：

```powershell
./scripts/check.ps1 -SkipInstall
```

脚本执行 Ruff、pytest 覆盖率、Alembic 往返、TypeScript、Vitest、生产构建、WPF Release 构建和桌面安全测试。

## Docker 空环境门禁

```powershell
Copy-Item .env.example .env
# 将 APP_SECRET_KEY 改为仅用于本地验收的随机值
./scripts/smoke-compose.ps1
```

执行前先确认 `docker version` 同时显示 Client 和 Server；仅安装 Docker CLI 而 Docker Desktop/WSL 2 引擎未就绪时不能通过该门禁。

脚本会删除本项目 Compose 卷、重新构建并等待服务就绪，然后用合成账号完成注册和登录，并检查 Web/Admin HTTP 响应。若项目路径包含中文等非 ASCII 字符，脚本会自动分配临时 ASCII 盘符以兼容 Docker BuildKit，并在结束时释放。默认结束后清理环境；调试时可使用 `-KeepEnvironment`。此脚本会清除当前 Compose 项目的数据库和 Redis 数据，不应用于含有需要保留数据的环境。

## 安全要求

1. `.env` 不进入版本库。
2. 测试账号、邮箱和候选密码必须是合成数据。
3. 不在日志中记录请求体、密码、Authorization、Cookie、TOTP 秘钥或一次性令牌。
4. 本地 SQLite 不复制到集成或生产环境。
5. 不用内存限流器替代集成/生产 Redis 验收。
6. 候选秘密不得进入浏览器持久存储、日志、审计详情或异常文本；揭示响应不得被缓存。
7. 桌面制品目录和安装包不得提交 Git；生产下载必须使用 HTTPS，且只有发布流水线可以把签名状态标记为 `verified`。
