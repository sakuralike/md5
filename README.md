# 密码侦探社

密码侦探社是一个以压缩包文件指纹为检索键、以本地解压验证证据维护候选密码可信度的系统。本仓库按照模块化单体方式组织 API，并包含用户 Web、管理端和 Windows 桌面端。

> 当前阶段：M4 第 8 次迭代已完成签名 HTTPS Webhook、提供商回执、通知投递指标、失败队列和幂等重放工作台；`risk-alert-sla-v1`、MFA 值班指派、事务通知 Outbox、候选关联降权、人工审核、举报/申诉、积分/信誉、奖励补偿及 M3 桌面发布闭环保持完成。当前工程估算为：功能代码约 92%、MVP 验收约 80%、生产上线准备度约 50%；该估算不替代真实提供商和目标环境验收。项目只使用合成测试数据，禁止提交真实密码、访问令牌或生产密钥。

## 仓库结构

```text
apps/
├─ api/                 # FastAPI 模块化单体和 Worker
├─ web/                 # Vue 3 用户端
├─ admin/               # Vue 3 管理端
└─ desktop-windows/     # .NET WPF 桌面端
packages/
├─ web-ui/              # Web/Admin 共享设计令牌
└─ api-contract/        # 前端共享 API 类型
infra/                  # Docker、Nginx、迁移和可观测性配置
docs/                   # ADR、API、安全、测试和开发记录
scripts/                # 本地开发与检查脚本
项目文档/               # 当前产品规格与实施计划
```

## 快速开始

### API（无需 Docker 的本地模式）

```powershell
./scripts/setup-api.ps1
./scripts/dev-api.ps1
```

API 默认使用本地 SQLite，仅用于开发；Swagger 位于 `http://127.0.0.1:8000/docs`。

### Web 与管理端

```powershell
pnpm install
pnpm dev:web
pnpm dev:admin
```

### Windows 桌面端

```powershell
dotnet build ./apps/desktop-windows/PasswordDetective.Desktop.csproj
```

### 容器环境

安装 Docker Desktop 后：

```powershell
Copy-Item .env.example .env
# 修改 APP_SECRET_KEY 后再启动
docker compose up --build

# 或执行会清理本项目 Compose 数据的空环境门禁
./scripts/smoke-compose.ps1
```

## 质量检查

```powershell
./scripts/check.ps1
```

## 开发基线

- [项目规格说明书](./项目文档/密码侦探社项目规格说明书-v3.0.md)
- [开发实施计划](./项目文档/密码侦探社开发实施计划-v1.0.md)
- [阶段状态](./docs/development/phase-status.md)
- [项目整体完成度审计](./docs/development/2026-08-02-completion-audit.md)
- [M4 第 8 次迭代记录](./docs/development/2026-08-03-m4-iteration-8.md)
- [M4 第 7 次迭代记录](./docs/development/2026-08-03-m4-iteration-7.md)
- [M4 第 6 次迭代记录](./docs/development/2026-08-03-m4-iteration-6.md)
- [M4 第 5 次迭代记录](./docs/development/2026-08-02-m4-iteration-5.md)
- [M4 第 4 次迭代记录](./docs/development/2026-08-02-m4-iteration-4.md)
- [M4 第 3 次迭代记录](./docs/development/2026-08-02-m4-iteration-3.md)
- [M4 第 2 次迭代记录](./docs/development/2026-08-02-m4-iteration-2.md)
- [M4 第 1 次迭代记录](./docs/development/2026-08-02-m4-iteration-1.md)
- [M3 第 4 次迭代记录](./docs/development/2026-08-02-m3-iteration-4.md)
- [M3 第 3 次迭代记录](./docs/development/2026-08-02-m3-iteration-3.md)
- [M3 第 2 次迭代记录](./docs/development/2026-08-02-m3-iteration-2.md)
- [M2 第 1 次迭代记录](./docs/development/2026-08-02-m2-iteration-1.md)
- [M1 第 2 次迭代记录](./docs/development/2026-08-02-m1-iteration-2.md)
- [主分支保护验收](./docs/development/branch-protection.md)
- [架构决策](./docs/adr/README.md)
- [初始威胁模型](./docs/threat-model/initial-threat-model.md)
