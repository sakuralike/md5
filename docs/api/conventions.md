# API 契约约定

## 基础约定

- 基础路径：`/api/v1`
- JSON 字段：`snake_case`
- 时间：ISO 8601 UTC
- 请求追踪：客户端可传 `X-Request-ID`，服务端始终回传。
- 创建贡献、回执和状态操作：使用 `Idempotency-Key`。

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
  "request_id": "req_01..."
}
```

错误信息不得用于枚举账号，不得回显密码、令牌、密钥或内部堆栈。
