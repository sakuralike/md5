# API 动态安全基线

- 建立日期：2026-08-09
- 适用范围：FastAPI `/api/v1` 动态预检
- 自动化入口：`pnpm security:dast`
- CI 作业：`dast-security`
- 首个完整通过运行：GitHub Actions `31340260242`

## 1. 目标与定位

本门禁在隔离 SQLite 数据库、内存限流器和非默认端口 `8011` 上启动独立 API，执行确定性黑盒探针，并把 JSON 报告、API 标准输出和错误输出保存到 `.local/security-dast/`。远端制品名为 `dast-security-evidence-<commit-sha>`，保留 30 天。

该基线用于阻断已知的低成本动态回归，不等同于完整 OWASP ZAP 扫描、认证后爬虫、人工渗透测试或生产环境安全评估。

## 2. 应用侧控制

`HttpSecurityMiddleware` 对 `/api/` 响应统一补充：

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: no-referrer`
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`
- 未由业务显式设置时使用 `Cache-Control: no-store`
- JSON 响应使用限制型 `Content-Security-Policy`

JSON 请求体默认上限为 `1,048,576` 字节，可通过 `MAX_JSON_BODY_BYTES` 在 `1 KiB` 至 `16 MiB` 范围内调整。中间件同时检查 `Content-Length` 并对分块请求实际累计字节，超过上限返回 `413 request.body_too_large`，不把请求体内容写入错误响应。

桌面更新制品上传使用 `application/octet-stream` 和独立的 `DESKTOP_UPDATE_MAX_ARTIFACT_BYTES` 流式限制，不受 JSON 上限替代或削弱。

## 3. 动态探针

当前报告固定包含 8 项：

1. 数据库和限流后端就绪检查。
2. 安全响应头与服务端生成请求号。
3. 匿名用户访问本人、隐私和管理端资源时的鉴权边界。
4. 配置来源 CORS 预检允许、非信任来源拒绝。
5. 不支持 HTTP 方法返回 `405` 且不暴露 traceback。
6. XSS 合成查询标记不反射。
7. 合成密码和令牌标记不出现在登录错误响应。
8. 超大 JSON 请求体返回 `413`。

任一检查失败，脚本返回非零退出码并阻断 `dast-security` 作业。

## 4. 本地执行

```powershell
pnpm security:dast

# 或显式指定隔离端口和证据目录
./scripts/dast-security-gate.ps1 `
  -PythonCommand ./apps/api/.venv/Scripts/python.exe `
  -Port 8011 `
  -OutputDirectory .local/security-dast
```

脚本只停止自己启动的 API 进程，不占用或终止开发端口 `8000`、`5173`、`5174`。

## 5. 已验证证据

- 本地 `check.ps1 -SkipInstall -IncludeSecurity` 通过，包括 109 项 API 测试、1 项真实 Redis 条件测试跳过、90.20% 覆盖率、11 项安全脚本测试、依赖/SAST/SBOM、前端和桌面门禁以及 8/8 动态探针。
- GitHub Actions `31339839339` 的新增 `dast-security` 作业通过，但静态安全作业因 Linux Ruff 检出脚本 shebang 与非可执行位不一致而失败。
- 移除不需要的 shebang 后，提交 `45af0d3` 对应运行 `31340260242` 的 9 个作业全部通过；下载的 DAST 报告为 `total=8`、`passed=8`、`failed=0`。

## 6. 尚未覆盖

- 两个已认证普通用户之间的对象级越权/BOLA 动态矩阵。
- 浏览器 Cookie 会话下的 CSRF、SameSite 和多标签重放专项。
- 管理员 MFA、一次性再认证和幂等键的动态滥用组合。
- 认证爬虫、参数模糊测试、批量资源消耗和长时间速率/并发攻击。
- OWASP ZAP 等通用扫描器、人工渗透、预生产与生产网络边界。

下一轮应优先补齐认证身份矩阵、幂等/再认证重放与资源消耗门禁，再进入恢复演练。
