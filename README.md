# 密码侦探社

密码侦探社是一个以压缩包文件指纹为检索键、以本地解压验证证据维护候选密码可信度的系统。本仓库按照模块化单体方式组织 API，并包含用户 Web、管理端和 Windows 桌面端。

> 当前阶段：WP2/WP3 主要业务与跨浏览器预检已形成自动化基线；WP4 第 4 轮已补齐已认证普通用户对象级边界和浏览器 Cookie CSRF/SameSite 动态门禁。管理员 MFA/再认证滥用、幂等重放、资源消耗、恢复、性能、可观测性和目标环境验收仍待后续轮次。项目只使用合成测试数据，禁止提交真实密码、访问令牌或生产密钥。

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

# 首次运行浏览器 E2E 前安装 Chromium
pnpm e2e:install
./scripts/check.ps1 -IncludeE2E

# 生产依赖审计、API SAST 与 SBOM
pnpm security:audit
# 隔离 API 动态安全基线
pnpm security:dast
# 或将静态与动态安全门禁并入统一检查
./scripts/check.ps1 -SkipInstall -IncludeSecurity
```

## 开发基线

- [项目规格说明书](./项目文档/密码侦探社项目规格说明书-v3.0.md)
- [开发实施计划](./项目文档/密码侦探社开发实施计划-v1.0.md)
- [阶段状态](./docs/development/phase-status.md)
- [安全与供应链门禁](./docs/security/supply-chain-gates.md)
- [发布镜像、Secret 与风险接受门禁](./docs/security/release-security-gates.md)
- [API 动态安全基线](./docs/security/dast-baseline.md)
- [WP4 第 4 次迭代记录](./docs/development/2026-08-10-wp4-iteration-4.md)
- [WP4 第 3 次迭代记录](./docs/development/2026-08-09-wp4-iteration-3.md)
- [WP4 第 2 次迭代记录](./docs/development/2026-08-09-wp4-iteration-2.md)
- [WP4 第 1 次迭代记录](./docs/development/2026-08-09-wp4-iteration-1.md)
- [WP3 第 11 次迭代记录](./docs/development/2026-08-09-wp3-iteration-11.md)
- [WP3 第 1 次迭代记录](./docs/development/2026-08-09-wp3-iteration-1.md)
- [WP2 第 1 次迭代记录](./docs/development/2026-08-08-wp2-iteration-1.md)
- [WP2 第 2 次迭代记录](./docs/development/2026-08-08-wp2-iteration-2.md)
- [项目整体完成度审计（2026-08-03 复核）](./docs/development/2026-08-03-completion-audit.md)
- [N2 第 6 次迭代记录](./docs/development/2026-08-04-n2-iteration-6.md)
- [N2 第 5 次迭代记录](./docs/development/2026-08-04-n2-iteration-5.md)
- [N2 第 4 次迭代记录](./docs/development/2026-08-03-n2-iteration-4.md)
- [N2 第 3 次迭代记录](./docs/development/2026-08-03-n2-iteration-3.md)
- [N2 第 2 次迭代记录](./docs/development/2026-08-03-n2-iteration-2.md)
- [N2 第 1 次迭代记录](./docs/development/2026-08-03-n2-iteration-1.md)
- [N1 第 4 次迭代记录](./docs/development/2026-08-03-n1-iteration-4.md)
- [M4 第 9 次迭代记录](./docs/development/2026-08-03-m4-iteration-9.md)
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
