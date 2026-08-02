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

默认开发数据库为 `apps/api/.local/password-detective.db`，默认限流后端为内存。该组合只用于本机单进程开发；集成和生产环境必须使用 MySQL 与 Redis。

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
```

本地/测试适配器使用 `APP_SECRET_KEY` 按用途派生候选加密密钥和 HMAC 去重密钥，仅用于开发闭环。生产部署必须接入独立 KMS/密钥管理适配器，并完成密钥版本轮换演练。

## Web 与 Admin

```powershell
pnpm install
pnpm dev:web
pnpm dev:admin
```

默认地址分别为 `http://localhost:5173` 和 `http://localhost:5174`。Web 本地指纹计算建议上限由 `VITE_MAX_ARCHIVE_SIZE_BYTES` 控制，默认 20 GiB；仍采用分块读取，不一次性载入内存。两者使用独立 HttpOnly 刷新 Cookie；如果更换端口或域名，必须同步更新 `CORS_ORIGINS`。生产环境必须设置 `BROWSER_COOKIE_SECURE=true` 并使用 HTTPS。

## 统一检查

```powershell
./scripts/check.ps1
```

已有依赖时可跳过安装：

```powershell
./scripts/check.ps1 -SkipInstall
```

脚本执行 Ruff、pytest 覆盖率、Alembic 往返、TypeScript、Vitest、生产构建和 WPF Release 构建。

## Docker 空环境门禁

```powershell
Copy-Item .env.example .env
# 将 APP_SECRET_KEY 改为仅用于本地验收的随机值
./scripts/smoke-compose.ps1
```

执行前先确认 `docker version` 同时显示 Client 和 Server；仅安装 Docker CLI 而 Docker Desktop/WSL 2 引擎未就绪时不能通过该门禁。

脚本会删除本项目 Compose 卷、重新构建并等待服务就绪，然后用合成账号完成注册和登录，并检查 Web/Admin HTTP 响应。默认结束后清理环境；调试时可使用 `-KeepEnvironment`。此脚本会清除当前 Compose 项目的数据库和 Redis 数据，不应用于含有需要保留数据的环境。

## 安全要求

1. `.env` 不进入版本库。
2. 测试账号、邮箱和候选密码必须是合成数据。
3. 不在日志中记录请求体、密码、Authorization、Cookie、TOTP 秘钥或一次性令牌。
4. 本地 SQLite 不复制到集成或生产环境。
5. 不用内存限流器替代集成/生产 Redis 验收。
6. 候选秘密不得进入浏览器持久存储、日志、审计详情或异常文本；揭示响应不得被缓存。
