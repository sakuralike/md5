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
- `PATCH /me/profile`
- `POST /me/security/password/change`
- `POST /me/security/totp/setup`
- `POST /me/security/totp/confirm`
- `DELETE /me/security/totp`
- `POST /admin/totp/setup`
- `POST /admin/totp/confirm`
- `POST /admin/totp/disable`

密码重置请求无论邮箱是否存在都返回相同消息，防止账号枚举。本人资料修改当前只开放用户名；邮箱变更必须使用后续独立验证流程。密码修改、TOTP 停用和账号删除申请统一先调用再认证接口，要求当前密码；启用 TOTP 的账号还需动态验证码。再认证接口签发默认 5 分钟有效、绑定当前会话族和精确目的的一次性凭据，仅保存 SHA-256 摘要并返回 `Cache-Control: no-store`，不使用 `Idempotency-Key`；消费接口仍可使用幂等键，幂等重放必须在消费前返回原成功响应。用户 TOTP 生成接口返回敏感密钥，因此只做限流，不将响应写入幂等缓存；确认和停用操作要求 `Idempotency-Key`。

Web 提供 `/verify-email`、`/forgot-password` 和 `/reset-password` 页面。邮件链接中的一次性凭证由页面读入内存后立即从地址栏移除，只通过 JSON 请求体提交；不得写入浏览器持久化存储、遥测或日志。浏览器登录支持可选 `totp_code`，已启用 TOTP 时由服务端强制校验。

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

候选密码使用 AES-GCM 密文保存，并用独立 HMAC 标签去重。反馈按 `correlation-v1` 先构建候选内关联组，再由 `verification-v2` 聚合：共享安装标识哈希或 IP 网段的传递关联反馈，在成功/失败两个结果维度内分别最多保留组内最高单条权重；两个独立成功且有效失败权重低于阈值时自动验证，三个独立失败或有效失败权重达到阈值时自动隔离。每次材料变化追加 `evidence_correlation_assessments` 聚合快照，所有自动状态变化写入 `record_state_events`。揭示审计只记录用户、档案、候选标识和结果，不记录秘密、密文或 nonce。当前每日揭示配额由 `DAILY_REVEAL_QUOTA` 配置；正式产品参数确定后同步更新规格和验收用例。

### 高风险用户操作再认证

| 方法 | 路径 | 认证 | 关键约束 |
|---|---|---|---|
| `POST` | `/me/security/reauthenticate` | 必需 | `purpose` 仅允许 `password_change`、`totp_disable`、`account_deletion`；当前密码必需，启用 TOTP 时还需动态码；签发短时一次性凭据，响应不缓存，不使用幂等键 |
| `POST` | `/me/security/password/change` | 必需 | 消费 `password_change` 凭据；业务写入与消费同事务；支持 `Idempotency-Key`，成功后撤销其他会话和未消费再认证凭据 |
| `DELETE` | `/me/security/totp` | 必需 | 消费 `totp_disable` 凭据；支持 `Idempotency-Key`，清理会话 MFA 标记 |
| `POST` | `/me/privacy/deletion-requests` | 必需 | 消费 `account_deletion` 凭据；支持 `Idempotency-Key`，进入可撤销宽限期 |

令牌原文只在签发响应中出现，不写入数据库、日志、审计或幂等响应；凭据绑定用户和当前会话族，过期、跨会话、跨目的或重复消费必须拒绝。

## 账号活动与隐私接口

| 方法 | 路径 | 认证 | 关键约束 |
|---|---|---|---|
| `GET` | `/me/reveals` | 必需 | 仅返回本人揭示的审计引用、时间、结果和掩码指纹摘要；不返回历史明文密码 |
| `GET` | `/me/authorization-declarations` | 必需 | 仅返回本人声明；记录当前版本、用途、来源、确认/撤回状态 |
| `POST` | `/me/authorization-declarations` | 必需 | `accepted=true`，由服务端注入当前声明版本；必须使用幂等键、限流和审计 |
| `POST` | `/me/privacy/exports` | 必需 | 返回 `202`；重复活动申请复用活动请求；本地可内联处理，部署环境可投递 Celery |
| `GET` | `/me/privacy/exports/{export_id}` | 必需 | 强制所有权校验；准备完成后返回短时下载凭证；过期时清理导出制品 |
| `POST` | `/me/privacy/exports/{export_id}/download` | 必需 | 提交短时凭证；一次性消费；响应不缓存；导出不含密码、候选秘密或 TOTP 密钥 |
| `POST` | `/me/privacy/deletion-requests` | 必需 | 消费 `account_deletion` 一次性再认证凭据；支持幂等和审计；进入可撤销宽限期 |
| `GET` | `/me/privacy/deletion-requests/current` | 必需 | 仅返回本人最近一次删除申请及状态 |
| `POST` | `/me/privacy/deletion-requests/{request_id}/cancel` | 必需 | 仅 `pending` 且未超过 `cancel_before` 时允许撤销；必须幂等和审计 |

导出状态为 `pending/processing/ready/failed/expired/downloaded`，删除状态为 `pending/cancelled/processing/completed`。Celery 任务会在宽限期结束后停用并去标识化账号，保留法定审计记录，清除授权声明、导出制品、账号动作令牌和会话中的可识别信息。

## 桌面安装、挑战与签名回执

| 方法 | 路径 | 认证 | 关键约束 |
|---|---|---|---|
| `POST` | `/desktop/installations` | 必需 | 注册 P-256 SPKI DER 公钥；安装 ID 不得跨账号或替换公钥；支持幂等重注册 |
| `GET` | `/desktop/installations` | 必需 | 仅返回当前账号的安装状态、公钥指纹、版本和回执计数 |
| `POST` | `/desktop/installations/{installation_id}/revoke` | 必需 | 撤销后不得创建挑战或提交回执 |
| `POST` | `/desktop/challenges` | 必需 | 绑定账号、安装、候选、档案指纹和客户端版本；随机 nonce 仅保存 SHA-256 摘要并在 300 秒后过期 |
| `POST` | `/desktop/receipts` | 必需 | 校验一次性挑战、ECDSA P-256/SHA-256 DER 签名、时间窗口、最低版本、字段绑定和防重放 |

回执规范载荷版本为 `desktop-receipt-v1`。客户端按固定顺序生成 UTF-8 `key=value` 行，时间统一为毫秒精度 UTC `Z`，末尾保留换行。签名覆盖挑战 ID/nonce、安装与账号、候选、档案指纹、候选密码 SHA-256 摘要、验证结果、压缩格式、客户端版本和验证时间。服务端只持久化候选摘要的 HMAC，不保存客户端提交的原始无盐摘要。

桌面端是不可信证据来源：签名只能证明某安装私钥生成了回执，不能证明客户端代码未被修改。有效回执仍进入 `verification-v2` 证据聚合，并接受候选内账号、安装和 IP 关联传递分组与动态限权；该分析不扩展为跨候选身份图谱。档案文件名、目录列表、文件内容和候选密码不得上传。

最低版本拒绝使用 `426 desktop.client_version_unsupported`，并在 `details` 中返回可供客户端展示的版本信息：

```json
{
  "code": "desktop.client_version_unsupported",
  "message": "客户端版本过低，最低要求为 0.2.0",
  "details": {
    "minimum_client_version": "0.2.0",
    "current_client_version": "0.1.0"
  },
  "request_id": "req_synthetic_desktop_upgrade"
}
```

`desktop.installation_revoked`、`desktop.installation_account_mismatch`、`desktop.installation_key_mismatch` 或 `desktop.installation_not_found` 表示本地身份不能继续使用，客户端可引导生成新的随机安装 ID/密钥并重新注册。`desktop.client_version_unsupported` 和 `desktop.installation_limit_reached` 不得通过重新生成身份绕过。

## 管理端候选审核与人工处置

| 方法 | 路径 | 认证 | 关键约束 |
|---|---|---|---|
| `GET` | `/admin/candidates?status=...&query=...&page=1&page_size=20` | 审核员/管理员 + MFA | 可按状态、候选/存档 ID 或指纹摘要筛选；只返回指纹、状态、计数和时间，不返回任何候选秘密字段 |
| `GET` | `/admin/candidates/{candidate_id}` | 审核员/管理员 + MFA | 返回聚合证据、关联组与动态限权摘要、不可变证据修订、自动/人工状态时间线和奖励校正时间线；仅展示账号/反馈标识与信号类型，不返回 IP、安装哈希、关联键或候选秘密 |
| `POST` | `/admin/candidates/{candidate_id}/transition` | 审核员/管理员 + MFA | 必须使用 16～128 字符 `Idempotency-Key`；使用 `moderation-v1` 状态矩阵和受控原因码；同事务写入人工状态事件、必要的首次验证奖励与奖励校正，并返回实际校正汇总 |

人工原因码按目标状态约束：`manual.evidence_conflict`/`manual.security_hold` 仅用于隔离，`manual.invalid_candidate`/`manual.policy_violation` 仅用于拒绝，`manual.review_reopened` 仅用于重新进入待验证，`manual.verified_by_review` 仅用于人工通过，`manual.quarantine_cleared` 用于解除隔离后进入待验证或已验证。

状态事件保存可选的 500 字符审核说明，但审计详情只保存原因码、前后状态、事件 ID 和奖励校正聚合值。`reward-compensation-v1` 按状态事件追加积分/信誉校正，不改写原始奖励；详情中的校正时间线仅展示受控字段。调用方不得在审核说明中放入密码、令牌、密钥或个人信息；API 响应、日志和审计均不得复制候选密码明文、密文、nonce、密钥版本或去重标签。

## 举报与申诉案件

| 方法 | 路径 | 认证 | 关键约束 |
|---|---|---|---|
| `POST` | `/trust/reports` | 登录 | 举报存在的候选；每小时限流；要求 16～128 字符 `Idempotency-Key`；说明最多 1000 字符 |
| `POST` | `/trust/appeals` | 登录 | 仅候选贡献者可对 `rejected/quarantined` 候选申诉；说明必填；每日限流；要求 `Idempotency-Key` |
| `POST` | `/trust/account-appeals` | 登录 | 仅为当前账号创建 `account_appeal`；客户端不得指定目标账号；受控原因/恢复动作；每日最多 3 次；要求 `Idempotency-Key` |
| `GET` | `/trust/cases?kind=...&page=1&page_size=20` | 登录 | 只返回当前用户提交的案件，不接受任意 reporter 参数 |
| `GET` | `/trust/cases/{case_id}` | 登录 | 仅案件提交者可读取详情与事件；其他用户统一返回 `404 trust.case_not_found` |
| `GET` | `/admin/trust-cases?kind=...&status=...&query=...` | 审核员/管理员 + MFA | 按类型、状态、案件/候选/目标账号/风险告警 ID 或提交人用户名筛选统一队列 |
| `GET` | `/admin/trust-cases/{case_id}` | 审核员/管理员 + MFA | 返回案件详情和不可变事件时间线 |
| `POST` | `/admin/trust-cases/{case_id}/transition` | 审核员/管理员 + MFA | 要求 `Idempotency-Key` 和 `expected_version`；状态和结果码必须匹配；写入不可变事件与脱敏审计；不承担最终原子副作用 |
| `POST` | `/admin/trust-cases/{case_id}/assign` | 审核员/管理员 + MFA | 要求 `Idempotency-Key` 和 `expected_version`；仅允许 `open/in_review` 案件指派给启用的审核员/管理员；写入负责人前后快照与脱敏审计 |
| `POST` | `/admin/trust-cases/{case_id}/reopen` | 审核员/管理员 + MFA | 要求 `Idempotency-Key` 和 `expected_version`；仅允许 `resolved/dismissed` 案件以 `admin.reopened` 重开；清理负责人和结论元数据 |

案件状态为 `open/in_review/resolved/dismissed`，每次管理写操作都递增 `trust_cases.version`。主体类型为 `candidate/account/risk_alert`，数据库约束保证候选、目标账号和风险告警三个引用中恰有一个与主体类型一致。通用 `transition` 不再承担关闭案件重开；关闭案件必须调用专用 `reopen`。进入 `in_review` 时保留已明确指派的负责人，否则由服务端设置当前操作者为负责人。版本不匹配统一返回 `409 trust.case_version_conflict`，响应只提供当前版本、状态和负责人 ID。账号申诉最终结论、候选/账号状态副作用、奖励/信誉补偿和结果通知 Outbox 仍等待 WP2 原子处置接口。

自由文本只用于案件详情和事件时间线，不复制到审计详情。账号申诉审计仅保留案件类型、主体类型、目标账号 ID、受控原因和期望动作；指派/重开审计仅保留结构化前后值、版本和事件 ID，不复制说明、证据摘要或管理员处理说明。调用方不得提交密码、令牌、密钥或个人信息；用户接口必须保持对象级私有，管理接口必须保持 MFA 门禁。

## 风险告警管理

| 方法 | 路径 | 认证 | 关键约束 |
|---|---|---|---|
| `GET` | `/admin/risk-alerts?kind=...&severity=...&status=...&assigned_to_id=...&overdue=true&query=...` | 审核员/管理员 + MFA | 按告警类型、严重度、状态、负责人、实时 SLA 超时和告警/候选 ID 查询；仅返回聚合证据 |
| `GET` | `/admin/risk-alerts/operators` | 审核员/管理员 + MFA | 仅返回状态正常、角色为 moderator/admin 且启用 TOTP 的可指派人员 |
| `GET` | `/admin/risk-alerts/{alert_id}` | 审核员/管理员 + MFA | 返回告警投影、SLA、负责人、不可变时间线和通知投递状态，不返回邮箱、IP、安装标识或关联键 |
| `POST` | `/admin/risk-alerts/{alert_id}/assign` | 审核员/管理员 + MFA | 要求 `Idempotency-Key`；只允许指派给可用 MFA 操作者，写入负责人变化事件、通知 Outbox 和最小披露审计 |
| `POST` | `/admin/risk-alerts/{alert_id}/transition` | 审核员/管理员 + MFA | 要求 `Idempotency-Key`；目标状态与结果码强匹配，写入不可变事件、通知 Outbox 与最小披露审计 |
| `GET` | `/admin/risk-alerts/notification-deliveries/metrics` | 审核员/管理员 + MFA | 返回状态总量、近 24 小时失败数、最老待发送时长和按提供商聚合指标 |
| `GET` | `/admin/risk-alerts/notification-deliveries?status=...&kind=...&provider=...` | 审核员/管理员 + MFA | 分页筛选投递记录；不返回邮箱、Webhook 地址、密钥或原始载荷 |
| `POST` | `/admin/risk-alerts/notification-deliveries/{notification_id}/replay` | 审核员/管理员 + MFA | 仅失败记录；要求 `Idempotency-Key`、受控原因和端点限流，复用原 Outbox 与去重键并写审计 |

`risk-alert-v1` 在 15 分钟内观察到至少 3 个独立当前失败组且失败权重不低于 3.0 时创建 `failure_surge/high` 告警。同一候选、类型和规则版本只保留一个活跃告警；处置状态为 `open/acknowledged/resolved`，已解决告警可受控重开。`risk-alert-sla-v1` 固定 15 分钟首次响应和 240 分钟解决目标；告警保存规则版本和绝对截止时间，Worker 扫描响应/解决超时并通过事务 Outbox 有限重试投递。首版不自动封禁账号或扣减信誉。

Outbox 类型为 `detected/assigned/acknowledgement_overdue/resolution_overdue/resolved/reopened`，状态为 `pending/sent/failed`。通知记录不复制接收地址；投递时从用户记录读取地址，载荷只包含投递 ID、类型、告警 ID、严重级别和适用截止时间。`notification-webhook-v1` 强制 HTTPS，并以 UTC 时间戳、规范 JSON 和 HMAC-SHA256 签名；投递表只保存提供商、回执、失败摘要和重放元数据。第三次失败进入终态，MFA 操作者可通过幂等重放接口恢复为待发送。

## 桌面更新发布与下载

| 方法 | 路径 | 认证 | 关键约束 |
|---|---|---|---|
| `GET` | `/desktop/updates/check?current_version=...&channel=stable&platform=windows&architecture=x64` | 匿名 | 仅选择相同目标的最高 `published` 版本；返回最低版本、强制升级、发布说明、SHA-256、大小、签名状态和后端下载地址 |
| `GET` | `/desktop/updates/{release_id}/download` | 匿名 | 仅下载 `published` 且存储完整性仍匹配的制品；响应含不可变缓存、ETag、`Digest` 和 `nosniff` |
| `POST` | `/admin/desktop-releases` | 管理员 + MFA | 创建 `draft` 发布记录；版本目标唯一，声明文件名、大小、SHA-256 和代码签名元数据 |
| `GET` | `/admin/desktop-releases` | 管理员 + MFA | 列出发布生命周期、上传状态和下载计数 |
| `PUT` | `/admin/desktop-releases/{release_id}/artifact` | 管理员 + MFA | 请求体为安装包原始字节流；按声明大小和 SHA-256 流式校验，通过后原子替换 |
| `POST` | `/admin/desktop-releases/{release_id}/publish` | 管理员 + MFA | 重新核验存储制品；生产环境只允许发布记录标记为 `verified` 且包含签名者与证书指纹 |
| `POST` | `/admin/desktop-releases/{release_id}/withdraw` | 管理员 + MFA | 将版本标记为 `withdrawn`，检查与下载入口立即停止提供该制品 |

发布生命周期固定为 `draft → published → withdrawn`。同一通道、平台、架构和版本只能存在一条记录；已发布记录不可覆盖制品，修复必须使用新版本。`stable` 与 `beta` 通道严格隔离，当前桌面 UI 默认只查询 `stable/windows/x64|arm64`。

服务端的 `code_signature_status=verified` 是受 MFA 保护的发布流程证明，不等价于客户端对 Authenticode 的本地密码学验证。首版桌面端只自动检查，不静默下载、不自动执行；用户点击后由系统浏览器打开同一后端返回的 HTTP(S) 下载入口，生产必须使用 HTTPS，并在安装前核验操作系统展示的签名者。

## 管理端治理仪表盘

| 方法 | 路径 | 认证 | 关键约束 |
|---|---|---|---|
| `GET` | `/admin/dashboard/summary?window_hours=24` | 审核员/管理员 + MFA | 时间窗口 1～720 小时；返回真实聚合指标、生成时间和治理队列快照 |

指标口径：

- 有效查询量只统计通过指纹格式校验并进入查询服务的请求；格式非法请求不计入。
- 查询命中以 `archive.search` 审计事件存在目标档案 ID 为准；事件不保存完整指纹，历史数据不回填。
- 新增贡献、已审计业务操作数和失败率按请求窗口统计；失败率是 `result != success` 的审计事件占比，不等同于全量 HTTP 错误率。
- 候选验证率、隔离量和治理队列为生成时快照；验证率以已验证候选数除以候选总数，零分母返回 `0`。
- 治理队列汇总待审核候选、处理中举报/申诉、未关闭风险告警、待处理隐私导出和账号删除申请。
- 接口只返回聚合计数，不返回指纹、候选密码、邮箱、IP、安装标识或用户自由文本。

## 管理端审计中心

| 方法 | 路径 | 认证 | 关键约束 |
|---|---|---|---|
| `GET` | `/admin/audit-logs` | 审核员/管理员 + MFA | 分页 1～100 条；支持动作、结果、目标类型、操作者、请求号、时间范围和综合搜索 |
| `GET` | `/admin/audit-logs/{audit_id}` | 审核员/管理员 + MFA | 返回操作者用户名/角色和服务端再次脱敏的详情，不返回邮箱或秘密材料 |
| `GET` | `/admin/audit-logs/export` | 审核员/管理员 + MFA | 当前筛选同步 CSV；单次最多 5000 条、每分钟最多 10 次，并写入 `admin.audit.export` |

- `created_from` 不得晚于 `created_to`；非法范围返回 `422 admin.audit.invalid_time_range`。
- 综合搜索只覆盖审计 ID、动作、目标类型、目标 ID、请求号和操作者用户名；通配符按普通字符转义。
- `details` 在输出前按键名递归脱敏，限制 4 层深度、每个对象 64 项、数组 20 项和字符串 256 字符；密码、令牌、Cookie、邮箱、Webhook、载荷和摘要等键值统一替换为 `[redacted]`。
- CSV 使用 UTF-8 BOM，危险公式前缀 `= + - @` 自动增加单引号；响应暴露 `Content-Disposition` 和 `X-Exported-Rows`。
- 列表和详情读取不写新的审计事件，避免查询审计产生递归记录；导出本身必须审计。超过导出上限返回 `422 admin.audit_export_too_large`。

## 管理端用户治理总览

| 方法 | 路径 | 认证 | 关键约束 |
|---|---|---|---|
| `GET` | `/admin/users?status=...&role=...&query=...&page=1&page_size=20` | **管理员 + MFA** | 仅 `admin` 角色可访问；按账号状态、角色、用户 ID/用户名/邮箱筛选；列表只返回脱敏邮箱和会话/MFA摘要 |
| `GET` | `/admin/users/{user_id}` | **管理员 + MFA** | 返回账号治理统计、积分余额、声望事件、提交/案件和隐私队列计数；不存在返回 `404 admin.user_not_found` |

- 用户治理读取接口不返回完整邮箱、密码、TOTP 密钥、刷新令牌、IP 或秘密材料；邮箱查询只用于服务端筛选，响应使用首字符掩码。
- 列表按注册时间和用户 ID 倒序分页；活跃会话定义为未撤销且未过期，会话总数与最近活跃时间只用于治理摘要。
- 用户治理读取保持最小披露；停用、恢复、会话撤销和普通角色受控变更已通过管理员近期再认证、原因码、幂等、乐观并发、对象保护和不可变审计开放。

## 管理端系统配置版本治理

| 方法 | 路径 | 认证 | 关键约束 |
|---|---|---|---|
| `GET` | `/admin/settings/versions?page=1&page_size=20` | 仅管理员 + MFA | 返回不可变版本摘要和 `published_version_id`；不返回秘密配置 |
| `GET` | `/admin/settings/versions/{version_id}` | 仅管理员 + MFA | 返回固定 Schema 快照及相对基线的逐字段差异 |
| `POST` | `/admin/settings/versions` | 仅管理员 + MFA | 要求 `Idempotency-Key`、`expected_base_version_id` 和结构化原因；只创建草稿，不直接生效 |
| `POST` | `/admin/settings/versions/{version_id}/publish` | 仅管理员 + MFA | 要求 `admin_settings_governance` 一次性再认证、预期当前发布版本、原因码和幂等键 |
| `POST` | `/admin/settings/versions/{version_id}/rollback` | 仅管理员 + MFA | 只能选择历史已发布版本；创建新的发布版本，不改写目标历史快照 |

首批 `operational-v1` 快照仅允许每日揭示配额、再认证 TTL、账号删除宽限期、桌面最低版本和升级下载缓存五个字段。Pydantic 在草稿入口执行类型、范围和版本格式校验；不接受任意键值、秘密、令牌或自由文本。

发布和回滚均使用当前生效版本进行乐观并发校验。服务端必须先检查冲突，再消费一次性再认证凭据；`409` 前置冲突不得消耗授权。成功后在同一事务更新 `system_settings` 运行时投影并写最小披露审计。幂等请求摘要不包含再认证令牌，缓存响应不得暴露该令牌。

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

## 本人积分与信誉

- `GET /api/v1/me/trust-profile`：返回本人信誉分、积分状态汇总、贡献和有效反馈统计。
- `GET /api/v1/me/points`：分页返回本人积分流水。
- `GET /api/v1/me/reputation`：分页返回本人不可变信誉事件。
- 三个端点均从认证主体确定用户，不接受目标用户 ID；积分状态为 `pending/posted/reversed`。
- 信誉事件使用 `reputation-v1`、受控原因码和引用唯一约束，分值范围为 0～100。
- 候选奖励失效或恢复时追加 `reward.contribution.invalidate`、`reward.verification.invalidate`、`reward.contribution.restore`、`reward.verification.restore` 事件；原始奖励不被删除或修改，信誉流水记录边界裁剪后的实际变化量。

## 管理端用户治理危险操作

| 方法 | 路径 | 认证 | 关键约束 |
|---|---|---|---|
| `POST` | `/admin/auth/reauthenticate` | 仅管理员 + MFA | 当前密码与 TOTP；按 `purpose` 签发短时、一次性、当前会话族绑定的 `admin_user_governance` 或 `admin_settings_governance` 凭据；响应 `no-store` |
| `PATCH` | `/admin/users/{user_id}/status` | 仅管理员 + MFA | 仅 `active/disabled`；要求一次性再认证、结构化原因、`expected_status` 和 `Idempotency-Key`；停用自动撤销活跃会话 |
| `POST` | `/admin/users/{user_id}/sessions/revoke` | 仅管理员 + MFA | 要求一次性再认证、结构化原因、`expected_active_session_count` 和 `Idempotency-Key` |

管理员治理凭据不得由公开用户再认证接口签发。对象级规则禁止管理员处置自身、其他管理员和服务账号；状态或会话计数冲突返回 `409` 且不消费凭据。成功响应可由幂等记录重放，但同一再认证令牌用于新的幂等请求必须返回 `401`。审计详情不得包含当前密码、TOTP、再认证令牌、完整邮箱、完整 IP 或自由文本。

受控角色变更已开放最小后端闭环：普通角色转换必须创建请求并由另一名管理员复核；管理员、服务账号、自身对象、批量处置和紧急撤权仍关闭。

## 管理端受控角色变更

| 方法 | 路径 | 认证 | 关键约束 |
|---|---|---|---|
| `GET` | `/admin/role-change-requests` | 管理员 + 当前会话 MFA | 分页、状态筛选、最小披露 |
| `POST` | `/admin/users/{user_id}/role-change-requests` | 管理员 + 当前会话 MFA | 用户治理一次性再认证、固定转换矩阵、对象保护、幂等和审计 |
| `POST` | `/admin/role-change-requests/{request_id}/approve` | 不同管理员 + 当前会话 MFA | 请求状态与目标角色乐观并发、一次性再认证、批准后撤销目标活跃会话 |
| `POST` | `/admin/role-change-requests/{request_id}/reject` | 不同管理员 + 当前会话 MFA | 请求状态乐观并发、一次性再认证、幂等和审计 |

当前允许 `user`、`trusted_contributor`、`moderator` 之间的固定转换；管理员、服务账号、申请人自身、非正常账号和批量处置不允许进入该入口。请求响应不得包含密码、TOTP、再认证令牌或完整邮箱。

Admin `/role-changes` 工作台提供状态筛选、分页、加载/空/错误态、详情、创建和双人批准/拒绝。密码、TOTP 和再认证令牌只允许在页面内存与单次请求体中短时存在；切换选中项、筛选、分页或任一敏感操作结束时必须清理，不得写入浏览器持久化存储、URL、日志或错误详情。


## 可观测性指标接口

`GET /metrics` 返回 Prometheus 文本格式，生产环境由网络策略限制抓取来源。HTTP 指标标签只允许方法、规范化路由模板和状态码；未匹配路径统一使用 `__unmatched__`。指标不得包含请求号、完整指纹、用户或对象标识、密码、令牌、Cookie、异常正文和自由文本。Worker 可用性通过 Redis 中 90 秒 TTL 的心跳存在性判断，队列积压只导出默认 Celery 队列长度。
