# 本地开发指南

## 前置条件

- Python 3.12+
- Node.js 与 pnpm
- .NET 10 SDK（Windows 桌面端）
- Docker Desktop（可选；容器联调时需要）

## API

```powershell
./scripts/setup-api.ps1
./scripts/dev-api.ps1
```

默认开发数据库为 `apps/api/.local/password-detective.db`。该模式只用于本机开发与测试；集成环境必须使用 MySQL。

## Web

```powershell
pnpm install
pnpm dev:web
```

## Admin

```powershell
pnpm dev:admin
```

## 检查

```powershell
./scripts/check.ps1
```

## 安全要求

1. `.env` 不进入版本库。
2. 测试账号和候选密码必须是合成数据。
3. 不在日志中记录请求体、密码、Authorization 或 Cookie。
4. 本地 SQLite 不复制到集成或生产环境。
