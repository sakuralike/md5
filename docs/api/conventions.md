# API 契约约定

## 基础约定

- 基础路径：`/api/v1`
- JSON 字段：`snake_case`
- 时间：ISO 8601 UTC
- 请求追踪：客户端可传 `X-Request-ID`，服务端始终回传。
- 创建贡献、反馈、回执和状态操作必须使用 `Idempotency-Key`。

## 客户端认证边界

| 客户端 | 登录/刷新入口 | 刷新令牌传输 |
|---|---|---|
| Windows/受信 API 客户端 | `/auth/login`、`/auth/refresh` | JSON；客户端安全存储 |
| 用户 Web | `/web/auth/login`、`/web/auth/refresh`、`/web/auth/logout` | `pd_web_refresh` HttpOnly Cookie |
| 管理端 | `/admin/auth/login`、`/admin/auth/refresh`、`/admin/auth/logout` | `pd_admin_refresh` HttpOnly Cookie |

浏览器 Cookie 使用 `SameSite=Lax` 和受限 Path；生产必须启用 `Secure`。浏览器认证端点校验 `Origin` 白名单。管理端登录需要特权角色，管理功能还要求已绑定并在当前会话验证 TOTP。

账号安全接口包括：

- `POST /auth/email/verify`
- `POST /auth/email/resend`
- `POST /auth/password/forgot`
- `POST /auth/password/reset`
- `POST /admin/totp/setup`
- `POST /admin/totp/confirm`
- `POST /admin/totp/disable`

密码重置请求无论邮箱是否存在都返回相同消息，防止账号枚举。

## 幂等约定

- `Idempotency-Key` 长度 16～128，只允许字母、数字、点、下划线、冒号和连字符。
- 作用域、所有者、密钥摘要和请求摘要共同决定一次操作。
- 相同键和相同请求在完成后返回缓存响应。
- 相同键用于不同请求返回 `409 request.idempotency_conflict`。
- 相同操作仍在处理时返回 `409 request.idempotency_in_progress`。
- 默认记录保留 24 小时；原始键和敏感请求体不入库。

## 档案查询与贡献接口

| 方法 | 路径 | 认证 | 关键约束 |
|---|---|---|---|
| `GET` | `/archives/search?fingerprint=...` | 可选 | 只接受完整 MD5/SHA-1/SHA-256/SHA-512 十六进制指纹；匿名仅返回匹配和状态元数据，登录用户可见遮挡候选 |
| `POST` | `/archives/submissions` | 必需 | 必须声明有权提交、提供 `Idempotency-Key`；重复候选合并提交证据，不重复保存秘密 |
| `POST` | `/archives/{archive_id}/reveal` | 必需 | 仅揭示 `verified` 候选；执行每日配额；响应使用 `Cache-Control: no-store` |
| `GET` | `/me/submissions` | 必需 | 返回当前用户贡献及 pending/后续状态，不返回候选密码明文或密文 |
| `POST` | `/candidates/{candidate_id}/feedback` | 必需 | `success/failure`；同一账号仅一个当前有效反馈；修改追加历史；必须提供 `Idempotency-Key` |
| `GET` | `/me/feedback` | 必需 | 分页返回当前用户反馈修订历史、规则版本和候选当前状态 |

候选密码使用 AES-GCM 密文保存，并用独立 HMAC 标签去重。反馈按 `verification-v1` 聚合：两个独立成功且失败权重低于阈值时自动验证，三个独立失败或失败权重达到阈值时自动隔离；所有自动状态变化写入 `record_state_events`。揭示审计只记录用户、档案、候选标识和结果，不记录秘密、密文或 nonce。当前每日揭示配额由 `DAILY_REVEAL_QUOTA` 配置；正式产品参数确定后同步更新规格和验收用例。

## 成功响应

资源接口直接返回资源；响应头包含 `X-Request-ID`。列表使用：

```json
{
  "items": [],
  "page": 1,
  "page_size": 20,
  "total": 0
}
```

## 错误响应

```json
{
  "code": "auth.invalid_credentials",
  "message": "用户名、邮箱或密码不正确",
  "details": {},
  "request_id": "req_synthetic_example"
}
```

错误信息不得用于枚举账号，不得回显密码、令牌、密钥、Cookie、TOTP 秘钥或内部堆栈。限流返回 `429 rate_limit.exceeded` 和重试秒数；Redis 保护后端不可用时返回 `503 rate_limit.backend_unavailable`。
