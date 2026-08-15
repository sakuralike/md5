# 第三方桌面端 API v1 开发者文档

> 状态：公开接入合同（v1）
> 更新日期：2026-08-15
> 适用对象：经密码侦探社管理员创建并审核通过的第三方桌面应用开发者

## 1. 接入边界

第三方桌面端 API 使用 OAuth 2.0 Authorization Code + PKCE（S256）授权，不向桌面程序发放或要求保存客户端密钥。当前应用登记流程为：

1. 管理员在管理端“第三方 API”工作区手动创建应用。
2. 管理员登记应用名称、开发者、说明、精确回调地址和普通 Scope。
3. 管理员审核应用；只有审核通过的应用可以发起用户授权。
4. 用户在官方 Web 授权页确认 Scope。
5. 桌面端使用一次性授权码和 PKCE verifier 换取 Token。

数据模型已经保留 `developer_self_service` 来源，后续可扩展为“开发者自助申请、管理员审核”，但 v1 不提供自助申请接口。

第三方桌面端不得：

- 调用管理端 API、用户审批或总哈希池管理接口。
- 上传候选密码或绕过本地验证、挑战、签名与防重放校验。
- 将 Access Token、Refresh Token、PKCE verifier、安装私钥或管理密钥写入日志。
- 使用 Web/Admin Token 代替第三方 Token；第三方 Access Token audience 独立。

## 2. 地址与版本

所有 API 路径均相对于：

```text
https://password-detective.example/api/v1
```

Web 授权页相对于站点根地址：

```text
https://password-detective.example/oauth/authorize
```

示例域名、ID、摘要和 Token 全部是合成数据，不能直接用于生产环境。

v1 当前稳定开放：

| 能力 | 方法与路径 | Scope |
| --- | --- | --- |
| 用户授权确认 | `GET/POST /third-party/oauth/consent` | 用户登录态 |
| 授权码换 Token / 刷新轮换 | `POST /third-party/oauth/token` | 无 Bearer Token |
| 主动撤销 Token 会话 | `POST /third-party/oauth/revoke` | 无 Bearer Token |
| 当前第三方 Principal 探针 | `GET /third-party/oauth/me` | `profile:read` |
| 安装实例注册与列表 | `POST/GET /third-party/installations` | `desktop:installations` |
| 撤销安装实例 | `POST /third-party/installations/{installation_id}/revoke` | `desktop:installations` |
| 创建验证挑战 | `POST /third-party/challenges` | `desktop:verification` |
| 提交签名回执 | `POST /third-party/verification-receipts` | `desktop:verification` |

`hash:read` 已进入应用与 Token Scope 合同，用于后续兼容扩展；当前版本尚未公开哈希详情/评论只读路由，客户端不能把获得该 Scope 等同于相关接口已上线。桌面公告、更新检查和下载适配也属于后续开发切片，不在本次稳定端点表内。

## 3. Scope

| Scope | 当前用途 | 授予规则 |
| --- | --- | --- |
| `profile:read` | 调用 `/third-party/oauth/me` 验证当前用户、应用和授权会话 | 管理员创建应用时登记，用户授权确认 |
| `hash:read` | 为后续哈希详情与评论只读接口预留 | 当前可进入 Token，但相关只读路由尚未公开 |
| `desktop:installations` | 注册、列出、撤销当前用户在当前应用下的安装实例 | 管理员登记，用户授权确认 |
| `desktop:verification` | 创建挑战、提交本地验证签名回执 | 管理员登记，用户授权确认 |
| `desktop:verification:trusted` | 成功回执允许进入可信验证通道 | 只能由管理员审核时明确授予，且应用必须同时具备 `desktop:verification` |

Scope 在授权请求和 Token 响应中使用空格分隔。客户端应按最小权限申请，不得依赖未返回的 Scope。

普通 `desktop:verification` 成功回执进入待验证通道：

```text
third_party_pending
```

管理员明确授予可信 Scope 后，成功回执进入可信通道：

```text
third_party_trusted
```

可信通道资格会同时检查应用状态和 Token Scope；应用暂停、撤销或授权失效后，既有 Token 不能继续调用。

## 4. PKCE 授权流程

### 4.1 生成 PKCE 参数

客户端生成：

- `code_verifier`：43～128 字符的高熵 Base64URL 字符串，仅保存在当前授权流程内存中。
- `code_challenge`：`BASE64URL(SHA256(ASCII(code_verifier)))`，去除 `=` 填充。
- `state`：至少 16 字符的不可预测随机值，用于阻断登录 CSRF 和回调串线。

只支持：

```text
code_challenge_method=S256
response_type=code
```

### 4.2 打开系统浏览器

```text
GET https://password-detective.example/oauth/authorize
  ?response_type=code
  &client_id=pdc_synthetic_desktop_01
  &redirect_uri=http%3A%2F%2F127.0.0.1%3A48731%2Fcallback
  &code_challenge=synthetic_pkce_challenge_abcdefghijklmnopqrstuvwxyz0123456789
  &code_challenge_method=S256
  &state=synthetic_state_0123456789abcdef
  &scope=profile%3Aread%20desktop%3Ainstallations%20desktop%3Averification
```

要求：

- 必须使用系统浏览器，不在桌面端内嵌登录表单。
- `redirect_uri` 必须与管理员登记值精确匹配。
- 回调中的 `state` 必须与本地保存值恒等比较；不一致时立即终止。
- 用户拒绝时，回调包含 OAuth 错误参数，客户端不得继续换 Token。

### 4.3 授权码换 Token

```http
POST /api/v1/third-party/oauth/token
Content-Type: application/json
```

```json
{
  "grant_type": "authorization_code",
  "client_id": "pdc_synthetic_desktop_01",
  "code": "synthetic_authorization_code_0123456789",
  "redirect_uri": "http://127.0.0.1:48731/callback",
  "code_verifier": "synthetic_verifier_abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
}
```

成功响应：

```json
{
  "access_token": "synthetic_access_token_not_for_production",
  "token_type": "Bearer",
  "expires_in": 900,
  "refresh_token": "synthetic_refresh_token_not_for_production",
  "scope": "profile:read desktop:installations desktop:verification"
}
```

授权码有效期为 5 分钟且只能使用一次。Access Token 当前有效期为 15 分钟；Refresh Token 当前有效期为 30 天。

### 4.4 Refresh Token 轮换

```json
{
  "grant_type": "refresh_token",
  "client_id": "pdc_synthetic_desktop_01",
  "refresh_token": "synthetic_refresh_token_not_for_production"
}
```

每次刷新成功都会返回新的 Access Token 和新的 Refresh Token。客户端必须原子替换旧 Refresh Token；旧 Token 再次使用会被视为重放，并撤销整个 Token family。

推荐保存顺序：

1. 收到并完整验证成功响应。
2. 将新 Refresh Token 写入操作系统安全凭据存储。
3. 确认持久化成功后删除旧 Token。
4. 任一步失败时重新走系统浏览器授权，不反复重放旧 Token。

### 4.5 撤销

```http
POST /api/v1/third-party/oauth/revoke
Content-Type: application/json
```

```json
{
  "client_id": "pdc_synthetic_desktop_01",
  "token": "synthetic_refresh_token_not_for_production",
  "token_type_hint": "refresh_token"
}
```

撤销接口是幂等操作。用户也可以在 Web `/account/authorized-applications` 页面撤销应用授权；该操作会同时使关联第三方会话失效。

## 5. Bearer Token 与 Principal

后续请求携带：

```http
Authorization: Bearer synthetic_access_token_not_for_production
```

Principal 探针：

```http
GET /api/v1/third-party/oauth/me
```

```json
{
  "user_id": "00000000-0000-4000-8000-000000000101",
  "client_id": "pdc_synthetic_desktop_01",
  "app_id": "00000000-0000-4000-8000-000000000201",
  "scopes": [
    "profile:read",
    "desktop:installations",
    "desktop:verification"
  ]
}
```

API 会在每次请求重新检查用户、应用、授权关系、Token 会话和有效期。应用暂停或撤销后，不需要等待 Access Token 自然过期。

## 6. 安装实例与公钥

第三方桌面端为每个本地安装实例生成独立 ECDSA P-256 密钥对：

- 私钥仅存储在操作系统安全存储或受保护的本地密钥容器中。
- 公钥使用 PEM 格式注册。
- `installation_id` 必须是当前应用内稳定且不可猜测的安装标识。
- 不同应用、用户或安装实例不能复用同一安装身份或公钥。

注册请求：

```http
POST /api/v1/third-party/installations
Authorization: Bearer synthetic_access_token_not_for_production
Content-Type: application/json
```

```json
{
  "installation_id": "synthetic-installation-0001",
  "public_key": "-----BEGIN PUBLIC KEY-----\nSYNTHETIC_PUBLIC_KEY_MATERIAL\n-----END PUBLIC KEY-----",
  "key_algorithm": "ecdsa-p256-sha256",
  "client_version": "1.0.0",
  "operating_system": "windows",
  "architecture": "x64"
}
```

列出当前应用和当前用户的安装实例：

```http
GET /api/v1/third-party/installations
Authorization: Bearer synthetic_access_token_not_for_production
```

撤销：

```http
POST /api/v1/third-party/installations/synthetic-installation-0001/revoke
Authorization: Bearer synthetic_access_token_not_for_production
```

撤销后的安装实例不能恢复，客户端应生成新安装 ID 和新密钥对。

## 7. 挑战、canonical payload 与签名回执

### 7.1 创建挑战

```http
POST /api/v1/third-party/challenges
Authorization: Bearer synthetic_access_token_not_for_production
Content-Type: application/json
```

```json
{
  "installation_id": "synthetic-installation-0001",
  "candidate_id": "00000000-0000-4000-8000-000000000301",
  "fingerprint_algorithm": "sha256",
  "fingerprint_digest": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "client_version": "1.0.0"
}
```

客户端必须使用服务端返回的 `challenge_id`、`challenge_nonce`、`account_id`、候选与指纹绑定字段生成回执，不能自行替换。

### 7.2 canonical payload v1

协议版本：

```text
desktop-receipt-v1
```

字段顺序固定如下：

1. `version`
2. `client_id`
3. `challenge_id`
4. `challenge_nonce`
5. `installation_id`
6. `account_id`
7. `candidate_id`
8. `fingerprint_algorithm`
9. `fingerprint_digest`
10. `candidate_digest`
11. `outcome`
12. `archive_format`
13. `client_version`
14. `verified_at`

编码规则：

```text
key=value\n
```

- 按上述顺序拼接全部字段。
- 最后一行也必须带换行符 `\n`。
- 整体使用 UTF-8 编码。
- `verified_at` 使用服务端兼容的 UTC ISO 8601 格式。
- `outcome` 使用 API 枚举值。
- 使用安装实例 ECDSA P-256 私钥和 SHA-256 对完整字节串签名。
- `signature` 使用 Base64 编码后放入 JSON。

合成 canonical payload：

```text
version=desktop-receipt-v1
client_id=pdc_synthetic_desktop_01
challenge_id=00000000-0000-4000-8000-000000000401
challenge_nonce=synthetic_nonce_0123456789abcdef
installation_id=synthetic-installation-0001
account_id=00000000-0000-4000-8000-000000000101
candidate_id=00000000-0000-4000-8000-000000000301
fingerprint_algorithm=sha256
fingerprint_digest=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
candidate_digest=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
outcome=success
archive_format=zip
client_version=1.0.0
verified_at=2026-08-15T12:00:00Z
```

### 7.3 提交回执

```http
POST /api/v1/third-party/verification-receipts
Authorization: Bearer synthetic_access_token_not_for_production
Content-Type: application/json
```

请求体包含创建挑战时的全部绑定字段，并增加 `client_id`、`candidate_digest`、`outcome`、`archive_format`、`verified_at` 和 `signature`。

成功响应中的 `trust_channel` 只会是：

```text
third_party_pending
third_party_trusted
```

挑战已使用、挑战过期、字段不匹配、签名错误、时间偏移过大或重复回执都会被拒绝。

## 8. 错误格式与重试

统一错误结构：

```json
{
  "code": "third_party_oauth.invalid_grant",
  "message": "授权凭据无效",
  "details": {},
  "request_id": "synthetic-request-id-0001"
}
```

常见错误：

| HTTP | `code` | 客户端处理 |
| --- | --- | --- |
| 400 | `third_party_oauth.invalid_request` | 修正参数，不原样重试 |
| 400 | `third_party_oauth.invalid_grant` | 丢弃授权码/Token，重新授权 |
| 400 | `third_party_oauth.unsupported_grant_type` | 仅使用 `authorization_code` 或 `refresh_token` |
| 400 | `third_party_oauth.refresh_token_expired` | 重新打开系统浏览器授权 |
| 400 | `third_party_oauth.refresh_token_reused` | Token family 已撤销，清除本地 Token 并重新授权 |
| 401 | `third_party_oauth.authentication_required` | 提供第三方 Bearer Token |
| 401 | `third_party_oauth.session_unavailable` | 清除 Token 并重新授权 |
| 403 | `third_party_oauth.insufficient_scope` | 不重试；重新申请并由用户确认所需 Scope |
| 403 | `third_party_desktop.installation_revoked` | 创建新安装身份和密钥对 |
| 404 | `third_party_desktop.installation_not_found` | 重新注册安装实例 |
| 404 | `third_party_desktop.challenge_not_found` | 重新创建挑战 |
| 409 | `third_party_desktop.challenge_replayed` | 禁止重放，重新创建挑战 |
| 409 | `third_party_desktop.challenge_expired` | 重新创建挑战 |
| 409 | `third_party_desktop.challenge_binding_mismatch` | 检查本地状态串线，不原样重试 |
| 409 | `third_party_desktop.receipt_clock_skew` | 校准系统时间后创建新挑战 |
| 409 | `third_party_desktop.receipt_replayed` | 视为已处理或查询业务状态，不重复提交 |
| 429 | 限流错误 | 遵循响应信息并使用指数退避和随机抖动 |

仅网络中断、网关 502/503/504 和明确允许重试的 429 可以自动重试。授权码交换、Refresh Token 轮换和签名回执属于防重放操作；客户端必须保存幂等业务状态，不能在无法判断服务端是否接收时无限重放。

## 9. Python 合成示例：PKCE 与 Token 交换

```python
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import urllib.parse
import urllib.request

SITE = "https://password-detective.example"
API = f"{SITE}/api/v1"
CLIENT_ID = "pdc_synthetic_desktop_01"
REDIRECT_URI = "http://127.0.0.1:48731/callback"

verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode("ascii")
challenge = base64.urlsafe_b64encode(
    hashlib.sha256(verifier.encode("ascii")).digest()
).rstrip(b"=").decode("ascii")
state = secrets.token_urlsafe(24)

query = urllib.parse.urlencode(
    {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "scope": "profile:read desktop:installations desktop:verification",
    }
)
print(f"Open system browser: {SITE}/oauth/authorize?{query}")

synthetic_code = "synthetic_authorization_code_0123456789"
payload = json.dumps(
    {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "code": synthetic_code,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier,
    }
).encode("utf-8")
request = urllib.request.Request(
    f"{API}/third-party/oauth/token",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
# response = json.loads(urllib.request.urlopen(request, timeout=15).read())
```

## 10. C# 合成示例：生成 PKCE

```csharp
using System;
using System.Security.Cryptography;
using System.Text;

static string Base64Url(byte[] value) => Convert.ToBase64String(value)
    .TrimEnd('=')
    .Replace('+', '-')
    .Replace('/', '_');

byte[] verifierBytes = RandomNumberGenerator.GetBytes(48);
string verifier = Base64Url(verifierBytes);
string challenge = Base64Url(SHA256.HashData(Encoding.ASCII.GetBytes(verifier)));
string state = Base64Url(RandomNumberGenerator.GetBytes(24));

string clientId = "pdc_synthetic_desktop_01";
string redirectUri = "http://127.0.0.1:48731/callback";
string scope = "profile:read desktop:installations desktop:verification";
string authorizeUrl =
    "https://password-detective.example/oauth/authorize" +
    $"?response_type=code&client_id={Uri.EscapeDataString(clientId)}" +
    $"&redirect_uri={Uri.EscapeDataString(redirectUri)}" +
    $"&code_challenge={Uri.EscapeDataString(challenge)}" +
    "&code_challenge_method=S256" +
    $"&state={Uri.EscapeDataString(state)}" +
    $"&scope={Uri.EscapeDataString(scope)}";

Console.WriteLine(authorizeUrl); // 使用系统浏览器打开
```

## 11. TypeScript 合成示例：构造 canonical payload

```typescript
const canonicalFields = [
  ["version", "desktop-receipt-v1"],
  ["client_id", "pdc_synthetic_desktop_01"],
  ["challenge_id", "00000000-0000-4000-8000-000000000401"],
  ["challenge_nonce", "synthetic_nonce_0123456789abcdef"],
  ["installation_id", "synthetic-installation-0001"],
  ["account_id", "00000000-0000-4000-8000-000000000101"],
  ["candidate_id", "00000000-0000-4000-8000-000000000301"],
  ["fingerprint_algorithm", "sha256"],
  ["fingerprint_digest", "a".repeat(64)],
  ["candidate_digest", "b".repeat(64)],
  ["outcome", "success"],
  ["archive_format", "zip"],
  ["client_version", "1.0.0"],
  ["verified_at", "2026-08-15T12:00:00Z"],
] as const;

const canonicalPayload = `${canonicalFields
  .map(([key, value]) => `${key}=${value}`)
  .join("\n")}\n`;
const payloadBytes = new TextEncoder().encode(canonicalPayload);

// 使用安装实例的 ECDSA P-256 私钥对 payloadBytes 执行 SHA-256 签名，
// 再将签名 Base64 编码写入 verification-receipts 请求体。
console.log(payloadBytes.byteLength);
```

## 12. 安全检查清单

- [ ] 使用系统浏览器和 PKCE S256，不在桌面端收集官方账号密码。
- [ ] 回调地址与管理员登记值精确一致，并校验 `state`。
- [ ] Token 和私钥保存到操作系统安全存储，不进入日志、崩溃报告或剪贴板。
- [ ] Refresh Token 成功轮换后原子替换，绝不重放旧值。
- [ ] 每个应用、用户和安装实例使用独立安装身份与密钥。
- [ ] canonical payload 字段、顺序、换行和 UTF-8 编码完全一致。
- [ ] 校验服务端返回 Scope，不假设申请的 Scope 全部获批。
- [ ] 遇到应用暂停、授权撤销或会话失效时清除本地 Token。
- [ ] 发布前验证错误处理、限流退避、时钟偏差和断网恢复。

## 13. 兼容性与变更

- v1 内新增可选字段和新端点属于向后兼容扩展。
- 既有字段语义、canonical payload 字段顺序或签名协议如需破坏性调整，必须发布新的协议版本。
- 客户端应忽略不认识的响应字段，但不能忽略未知 `trust_channel`、签名协议版本或错误码对应的安全失败。
- 稳定 TypeScript 合同位于 `packages/api-contract/src/index.ts`，端点常量、Scope、Grant Type 和 canonical 字段顺序应从该包引用，而不是在多个客户端内手工复制。
