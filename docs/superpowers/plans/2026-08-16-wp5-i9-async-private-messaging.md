# WP5-I9 一对一异步私信 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在既有社区、关系、通知和隐私治理边界内交付可审计的一对一异步私信：安全创建会话、发送和读取加密消息、归档/静音、最小化通知以及 Web 端收件箱旅程。

**Architecture:** 私信以独立 `direct_message_service.py` 作为业务边界，复用社区关系、通用幂等与通知 outbox，绝不把正文混入通知、日志或候选密码密钥域。规范化参与者对、成员状态和顺序消息表仅保存必要元数据，正文使用单独版本化 AES-GCM keyring 加密。Vue 端通过社区服务层和两个受保护页面承载会话列表与详情。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy、Alembic、Pydantic v2、cryptography AES-GCM、Pytest、Vue 3、TypeScript strict、Shadcn-Vue、Tailwind CSS、Vitest、Playwright、pnpm。

---

## 实施约束

- 仅实现 1:1 异步私信；不做群聊、私信 WS/SSE、附件、编辑/删除、举报/审核队列或实际邮件通知。
- 私信正文、nonce、私信密钥和可逆密文不得进入通知预览、审计 details、日志、metrics 或 outbox。
- 创建会话用公开 `recipient_username`，由服务端解析 ID，避免公开资料泄露内部 UUID；Task 4 要同步精化已确认规格和变更记录。
- 仅在隔离 worktree 的 `codex/wp5-i9-async-private-messaging` 分支操作；不触碰原工作区未关联修改。
- 所有写 API 需要 `Idempotency-Key`，复用 `core/idempotency.py`，scope 为 `community.direct.*`。

## 文件结构

| 路径 | 责任 |
| --- | --- |
| `apps/api/src/password_detective/core/direct_message_crypto.py` | 4,000-byte 正文校验、版本化 AES-GCM 加解密、keyring 装配。 |
| `apps/api/src/password_detective/core/config.py` | 独立 `DIRECT_MESSAGE_*` 配置与文件型密钥校验。 |
| `apps/api/src/password_detective/db/models/community.py` | 会话、成员、加密消息模型及通知枚举。 |
| `apps/api/alembic/versions/20260816_0044_add_community_direct_messages.py` | 表、外键、唯一约束、排序索引。 |
| `apps/api/src/password_detective/modules/community/direct_message_service.py` | 授权、分页、发送、状态、通知。 |
| `apps/api/src/password_detective/modules/community/{schemas.py,router.py}` | REST 请求/响应及路由。 |
| `apps/api/src/password_detective/modules/account_privacy/service.py` | 私信导出与账户删除。 |
| `packages/api-contract/src/index.ts`、`apps/web/src/services/community.ts` | 共享 TS 契约和 API 客户端。 |
| `apps/web/src/pages/Community{Messages,Conversation}Page.vue` | 收件箱及会话详情。 |
| `apps/web/src/pages/CommunityProfilePage.vue`、`apps/web/src/router/index.ts` | 资料入口和受保护路由。 |
| `apps/api/tests/test_{direct_message_crypto,community_direct_messages,migration_0044_direct_messages}.py` | 后端、加密和迁移测试。 |
| `apps/web/src/pages/Community{Messages,Conversation}Page.test.ts`、`tests/e2e/web-community-messages.spec.ts` | SSR 和三浏览器回归。 |

### Task 1: 修复 I8 合并基线的重复契约导入

**Files:**
- Modify: `packages/api-contract/src/index.test.ts:1-18`

- [ ] **Step 1: 复现已确认基线错误**

Run: `pnpm --filter @password-detective/api-contract typecheck`

Expected: FAIL，`index.test.ts` 对 `isPrivilegedRole`、`THIRD_PARTY_API_V1_PATHS`、`THIRD_PARTY_API_V1_SCOPES` 报 `TS2300 Duplicate identifier`。

- [ ] **Step 2: 写最小修复，不删除已有断言**

将导入块恢复为下面唯一集合，保留社区搜索和第三方 API 的所有现有测试：

```ts
import {
  ApiError,
  COMMUNITY_SEARCH_MODES,
  COMMUNITY_SEARCH_RESULT_TYPES,
  isPrivilegedRole,
  THIRD_PARTY_API_V1_PATHS,
  THIRD_PARTY_API_V1_SCOPES,
  THIRD_PARTY_REQUESTABLE_SCOPE_OPTIONS,
  THIRD_PARTY_OAUTH_GRANT_TYPES,
  THIRD_PARTY_RECEIPT_CANONICAL_FIELDS,
} from "./index";
```

- [ ] **Step 3: 验证并提交独立修复**

Run: `pnpm --filter @password-detective/api-contract typecheck && pnpm --filter @password-detective/api-contract test`

Expected: PASS。

```powershell
git add packages/api-contract/src/index.test.ts
git commit -m "fix(contract): remove duplicate merge imports"
```

### Task 2: 建立独立私信加密域与配置

**Files:**
- Create: `apps/api/src/password_detective/core/direct_message_crypto.py`
- Modify: `apps/api/src/password_detective/core/config.py`
- Create: `apps/api/tests/test_direct_message_crypto.py`
- Modify: `apps/api/tests/test_config.py`

- [ ] **Step 1: 写失败的 vault/config 测试**

```python
def test_direct_message_vault_round_trips_only_with_its_own_keyring() -> None:
    settings = Settings(app_env="test", direct_message_key_version="v2", direct_message_keyring='{"v1":"old-secret","v2":"active-secret"}')
    encrypted = build_direct_message_vault(settings).encrypt("合成私信正文")
    assert encrypted.ciphertext != "合成私信正文"
    assert build_direct_message_vault(settings).decrypt(**encrypted.__dict__) == "合成私信正文"


def test_direct_message_vault_rejects_tampered_ciphertext() -> None:
    encrypted = build_direct_message_vault(Settings(app_env="test")).encrypt("synthetic")
    with pytest.raises(AppError, match="私信暂时无法读取"):
        build_direct_message_vault(Settings(app_env="test")).decrypt(ciphertext=encrypted.ciphertext[:-2] + "AA", nonce=encrypted.nonce, key_version=encrypted.key_version)
```

同时覆盖空/超长正文、keyring 漏活动版本、重复 JSON key、生产短密钥、`DIRECT_MESSAGE_KEYRING_FILE`。

- [ ] **Step 2: 确认测试先失败**

Run: `apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_direct_message_crypto.py apps/api/tests/test_config.py -q`

Expected: FAIL，因为模块和设置字段不存在。

- [ ] **Step 3: 写最小配置和加密实现**

在 `Settings` 及 `FILE_BACKED_SETTING_ENVIRONMENTS` 添加：

```python
direct_message_key_version: str = Field(default="v1", min_length=1, max_length=32)
direct_message_keyring: SecretStr = SecretStr("")
"direct_message_key_version": "DIRECT_MESSAGE_KEY_VERSION",
"direct_message_keyring": "DIRECT_MESSAGE_KEYRING",
```

新增 `direct_message_key_map`，沿用 candidate keyring 的无重复 JSON、版本、最大 8 个、生产至少 32 字符校验。创建下列 API，不含 dedup tag：

```python
@dataclass(frozen=True)
class EncryptedDirectMessage:
    ciphertext: str
    nonce: str
    key_version: str

class DirectMessageVault:
    def encrypt(self, message: str) -> EncryptedDirectMessage: pass
    def decrypt(self, *, ciphertext: str, nonce: str, key_version: str) -> str: pass

def build_direct_message_vault(settings: Settings) -> DirectMessageVault: pass
```

用 12-byte nonce、`key_version` AAD 与 domain-separated 派生：

```python
hmac.new(master_secret, b"password-detective:community-direct-message:" + key_version.encode("utf-8"), hashlib.sha256).digest()
```

将 base64、认证标签、未知 key、UTF-8 错误统一为 `AppError("community.direct_message_unavailable", "私信暂时无法读取", 500)`。

- [ ] **Step 4: 验证并提交**

Run: `apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_direct_message_crypto.py apps/api/tests/test_config.py -q`

Expected: PASS。

```powershell
git add apps/api/src/password_detective/core/config.py apps/api/src/password_detective/core/direct_message_crypto.py apps/api/tests/test_direct_message_crypto.py apps/api/tests/test_config.py
git commit -m "feat(community): add direct message encryption vault"
```

### Task 3: 增加持久化模型、通知枚举和迁移

**Files:**
- Modify: `apps/api/src/password_detective/db/models/community.py`
- Modify: `apps/api/src/password_detective/db/models/__init__.py`
- Create: `apps/api/alembic/versions/20260816_0044_add_community_direct_messages.py`
- Create: `apps/api/tests/test_migration_0044_direct_messages.py`

- [ ] **Step 1: 写迁移和元数据失败测试**

```python
def test_release_migrations_converge_at_direct_messages_head() -> None:
    assert ScriptDirectory.from_config(config).get_heads() == ["20260816_0044"]

def test_direct_message_tables_have_canonical_pair_constraints() -> None:
    table = Base.metadata.tables["community_direct_conversations"]
    assert "uq_community_direct_conversation_pair" in {item.name for item in table.constraints}
```

- [ ] **Step 2: 运行以确认失败**

Run: `apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_migration_0044_direct_messages.py -q`

Expected: FAIL，head 为 `20260816_0043` 且表不存在。

- [ ] **Step 3: 实现三张最小表**

定义 `CommunityDirectConversation`、`CommunityDirectConversationMember`、`CommunityDirectMessage`，并导出到 `db/models/__init__.py`。会话存 `participant_low_id` / `participant_high_id`；成员存 `last_read_sequence=0`、`archived_at`、`muted_until`；消息存 `ciphertext`、`nonce`、`key_version`、`client_message_id`、单调 `sequence`。

```python
UniqueConstraint("participant_low_id", "participant_high_id", name="uq_community_direct_conversation_pair")
UniqueConstraint("conversation_id", "user_id", name="uq_community_direct_member")
UniqueConstraint("conversation_id", "sequence", name="uq_community_direct_message_sequence")
UniqueConstraint("sender_id", "client_message_id", name="uq_community_direct_sender_client_message")
```

在现有枚举增加 `CommunityNotificationKind.DIRECT_MESSAGE` 与 `CommunityNotificationSource.DIRECT_MESSAGE`。

- [ ] **Step 4: 写 `20260816_0044` 迁移**

`down_revision = "20260816_0043"`；创建三张表、上述约束及：

```python
op.create_index("ix_community_direct_message_conversation_sequence", "community_direct_messages", ["conversation_id", "sequence"])
op.create_index("ix_community_direct_member_user_updated", "community_direct_conversation_members", ["user_id", "updated_at"])
```

`downgrade()` 按消息、成员、会话逆序删除。

- [ ] **Step 5: 验证并提交**

Run: `apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_migration_0044_direct_messages.py -q`

Expected: PASS，唯一 head 为 `20260816_0044`。

```powershell
git add apps/api/src/password_detective/db/models/community.py apps/api/src/password_detective/db/models/__init__.py apps/api/alembic/versions/20260816_0044_add_community_direct_messages.py apps/api/tests/test_migration_0044_direct_messages.py
git commit -m "feat(community): persist direct message conversations"
```


### Task 4: 固化 Pydantic、REST 与 TypeScript 契约

**Files:**
- Modify: `apps/api/src/password_detective/modules/community/schemas.py`
- Modify: `packages/api-contract/src/index.ts`
- Modify: `packages/api-contract/src/index.test.ts`
- Modify: `docs/superpowers/specs/2026-08-16-wp5-i9-async-private-messaging-design.md`
- Modify: `项目文档/文档变更记录.md`

- [ ] **Step 1: 写请求校验和 TS 契约失败测试**

```python
def test_direct_message_request_normalizes_and_rejects_blank_body() -> None:
    assert CommunityDirectMessageCreateRequest(body="  合成内容  ", client_message_id="c-1").body == "合成内容"
    with pytest.raises(ValidationError):
        CommunityDirectMessageCreateRequest(body=" \
 ", client_message_id="c-1")
```

```ts
const message: CommunityDirectMessageResponse = { id: "message-1", conversation_id: "conversation-1", sender_username: "synthetic_sender", body: "仅用于契约测试的合成正文", sequence: 1, created_at: "2026-08-16T00:00:00Z" };
expect(message.sequence).toBe(1);
```

- [ ] **Step 2: 运行失败测试**

Run: `apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_community_direct_messages.py -q -k schema; pnpm --filter @password-detective/api-contract typecheck`

Expected: FAIL，私信 schema 和 TS 类型尚不存在。

- [ ] **Step 3: 实现请求/响应模型并同步共享契约**

```python
class CommunityDirectConversationCreateRequest(BaseModel):
    recipient_username: str = Field(min_length=3, max_length=64)

class CommunityDirectMessageCreateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    client_message_id: str = Field(min_length=1, max_length=72)

class CommunityDirectReadStateUpdateRequest(BaseModel):
    last_read_sequence: int = Field(ge=0)

class CommunityDirectMemberStateUpdateRequest(BaseModel):
    archived: bool | None = None
    muted_until: datetime | None = None
```

定义会话、会话列表、消息、消息列表响应。返回只含对方 username/display_name/avatar、序列、读取/归档/静音状态和 cursor；**不得**含 `ciphertext`、`nonce`、`key_version`。在 `packages/api-contract/src/index.ts` 写等值 interface/type，并把 `direct_message` 加入通知联合类型。

同步设计说明中 `recipient_user_id` 为 `recipient_username`，并在变更记录写明“不公开内部 UUID”的契约精化。

- [ ] **Step 4: 验证并提交**

Run: `apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_community_direct_messages.py -q -k schema; pnpm --filter @password-detective/api-contract typecheck; pnpm --filter @password-detective/api-contract test`

Expected: PASS。

```powershell
git add apps/api/src/password_detective/modules/community/schemas.py packages/api-contract/src/index.ts packages/api-contract/src/index.test.ts docs/superpowers/specs/2026-08-16-wp5-i9-async-private-messaging-design.md 项目文档/文档变更记录.md
git commit -m "feat(community): define direct message contracts"
```

### Task 5: 实现授权门、canonical 会话与列表分页

**Files:**
- Create: `apps/api/src/password_detective/modules/community/direct_message_service.py`
- Create: `apps/api/tests/test_community_direct_messages.py`

- [ ] **Step 1: 写访问控制与 canonical pair 失败测试**

```python
def test_create_direct_conversation_rejects_self_blocked_disabled_and_policy(client):
    alice = _register_login(client, "dm_alice")
    assert _create_conversation(client, alice, "dm_alice").json()["code"] == "DIRECT_MESSAGE_SELF_FORBIDDEN"
    # 分别设置目标禁用、任一方向 block、message_policy=none，并断言无会话记录。

def test_create_direct_conversation_is_a_canonical_pair(client):
    alice, bob = _register_login(client, "dm_pair_alice"), _register_login(client, "dm_pair_bob")
    assert _create_conversation(client, alice, "dm_pair_bob").json()["id"] == _create_conversation(client, bob, "dm_pair_alice").json()["id"]
```

添加非成员读会话为 `DIRECT_MESSAGE_NOT_PARTICIPANT`、归档会话不在默认列表、同 timestamp cursor 不丢第二项。

- [ ] **Step 2: 运行失败测试**

Run: `apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_community_direct_messages.py -q -k "conversation and not router"`

Expected: FAIL，因为服务模块尚不存在。

- [ ] **Step 3: 实现服务边界和游标**

```python
def _require_direct_message_access(db: Session, *, sender: User, recipient: User, action: str) -> None: pass
def _get_member_conversation(db: Session, *, conversation_id: str, user_id: str) -> CommunityDirectConversation: pass
def create_direct_conversation(db: Session, *, principal: Principal, payload: CommunityDirectConversationCreateRequest) -> CommunityDirectConversationResponse: pass
def list_direct_conversations(db: Session, *, principal: Principal, cursor: str | None, include_archived: bool) -> CommunityDirectConversationListResponse: pass
```

依次检查活动主体、目标 `UserStatus.ACTIVE`、非本人、`users_block_each_other` 和目标 `CommunityUserProfile.message_policy`；`EVERYONE` 放行，`FOLLOWING` 仅目标已关注发送者时放行，`NONE` 拒绝。使用精确业务码：自发 `DIRECT_MESSAGE_SELF_FORBIDDEN`、禁用 `DIRECT_MESSAGE_ACCOUNT_UNAVAILABLE`、策略/拉黑 `DIRECT_MESSAGE_UNAVAILABLE`、非成员 `DIRECT_MESSAGE_NOT_PARTICIPANT`。

按 ID 排序写 low/high，写两个 member；唯一冲突重查同 pair。列表仅读当前 member，默认排除 `archived_at is not None`，按 `last_message_at DESC, id DESC`；cursor base64url JSON 同时编码时间和 ID。

- [ ] **Step 4: 验证并提交**

Run: `apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_community_direct_messages.py -q -k "conversation and not router"`

Expected: PASS。

```powershell
git add apps/api/src/password_detective/modules/community/direct_message_service.py apps/api/tests/test_community_direct_messages.py
git commit -m "feat(community): add direct conversation access service"
```

### Task 6: 实现加密写入、读取/成员状态和最小通知

**Files:**
- Modify: `apps/api/src/password_detective/modules/community/direct_message_service.py`
- Modify: `apps/api/src/password_detective/modules/community/notification_service.py`
- Modify: `apps/api/tests/test_community_direct_messages.py`
- Modify: `apps/api/tests/test_community_notification_outbox_admin.py`

- [ ] **Step 1: 写发送安全边界失败测试**

```python
def test_send_message_encrypts_storage_and_creates_no_plaintext_notification(client):
    alice, bob, conversation_id = _conversation_with_two_users(client)
    response = _send_message(client, alice, conversation_id, "只用于测试的合成私信", "client-1")
    assert response.status_code == 201
    with client.app.state.database.session_factory() as db:
        stored, notification = db.scalar(select(CommunityDirectMessage)), db.scalar(select(CommunityNotification))
        assert stored.ciphertext != "只用于测试的合成私信"
        assert stored.nonce
        assert notification.preview == "你收到一条新私信"
        assert "合成私信" not in notification.preview
```

覆盖同 key 同 payload 回放、同 key 不同 payload 的 `409 DIRECT_MESSAGE_IDEMPOTENCY_CONFLICT`、read state 只前进、归档/静音仅本人、拉黑后旧会话不可读/不可发。

- [ ] **Step 2: 运行失败测试**

Run: `apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_community_direct_messages.py apps/api/tests/test_community_notification_outbox_admin.py -q -k "direct or notification"`

Expected: FAIL，写路径尚不存在。

- [ ] **Step 3: 实现单事务写路径**

```python
def send_direct_message(pass, idempotency_key: str) -> CommunityDirectMessageResponse: pass
def list_direct_messages(pass) -> CommunityDirectMessageListResponse: pass
def update_direct_read_state(pass) -> CommunityDirectConversationResponse: pass
def update_direct_member_state(pass) -> CommunityDirectConversationResponse: pass
```

锁定会话、再次授权、取 `max(sequence)+1`、调用 `build_direct_message_vault(settings).encrypt(payload.body)`，更新会话/成员并清除接收方 `archived_at`。通知只用固定预览：

```python
notification = create_notification(db, recipient_id=recipient.id, actor_id=sender.id, kind=CommunityNotificationKind.DIRECT_MESSAGE, source_type=CommunityNotificationSource.DIRECT_MESSAGE, source_id=message.id, preview="你收到一条新私信")
if notification is not None and recipient_member.muted_until is None:
    queue_notification_event(db, notification)
```

让通知投递在双方 block 后用 `community.notification_visibility_revoked` 终止；偏好关闭保留最小通知记录但不投递，member 静音不建 outbox。读取只对成员解密，失败统一 `community.direct_message_unavailable`。

- [ ] **Step 4: 验证并提交**

Run: `apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_community_direct_messages.py apps/api/tests/test_community_notification_outbox_admin.py -q`

Expected: PASS，DB、通知、API JSON 无原始正文泄漏。

```powershell
git add apps/api/src/password_detective/modules/community/direct_message_service.py apps/api/src/password_detective/modules/community/notification_service.py apps/api/tests/test_community_direct_messages.py apps/api/tests/test_community_notification_outbox_admin.py
git commit -m "feat(community): send encrypted direct messages"
```


### Task 7: 暴露受限 REST API、幂等和限流

**Files:**
- Modify: `apps/api/src/password_detective/modules/community/router.py`
- Modify: `apps/api/tests/test_community_direct_messages.py`

- [ ] **Step 1: 写 6 个端点的失败测试**

```python
def test_direct_message_routes_require_auth_and_idempotency(client):
    assert client.get("/api/v1/community/direct-conversations").status_code == 401
    token = _register_login(client, "dm_router_user")
    response = client.post("/api/v1/community/direct-conversations", json={"recipient_username": "other_user"}, headers=_auth(token))
    assert response.status_code == 422
    assert response.json()["code"] == "idempotency.key_required"
```

覆盖 GET 会话、GET 消息、POST 会话、POST 消息、PATCH read-state、PATCH member-state 的 401/403/404/409/422，发送 30/min、创建 20/hour。

- [ ] **Step 2: 确认失败后添加路由**

Run: `apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_community_direct_messages.py -q -k router`

Expected: FAIL，当前 API 为 404。

```python
@router.post("/direct-conversations", response_model=CommunityDirectConversationResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(rate_limit("community.direct.create", limit=20, window_seconds=3600))])
def create_direct_conversation(pass): pass

@router.get("/direct-conversations", response_model=CommunityDirectConversationListResponse)
def list_direct_conversations(pass): pass

@router.get("/direct-conversations/{conversation_id}/messages", response_model=CommunityDirectMessageListResponse)
def list_direct_messages(pass): pass

@router.post("/direct-conversations/{conversation_id}/messages", response_model=CommunityDirectMessageResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(rate_limit("community.direct.send", limit=30, window_seconds=60))])
def create_direct_message(pass): pass
```

添加 `PATCH /{conversation_id}/read-state` 和 `PATCH /{conversation_id}/member-state`。所有 POST/PATCH 调用现有 `_mutate_with_idempotency`，以 `payload.model_dump(mode="json")` 计算请求摘要，并分别使用 `community.direct.create`、`community.direct.send`、`community.direct.read_state`、`community.direct.member_state` scope。

- [ ] **Step 3: 验证并提交**

Run: `apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_community_direct_messages.py -q`

Expected: PASS。

```powershell
git add apps/api/src/password_detective/modules/community/router.py apps/api/tests/test_community_direct_messages.py
git commit -m "feat(community): expose direct message API"
```

### Task 8: 接入隐私导出、账户删除和需求追踪

**Files:**
- Modify: `apps/api/src/password_detective/modules/account_privacy/service.py`
- Modify: `apps/api/tests/test_account_privacy.py`
- Modify: `项目文档/需求追踪矩阵.md`
- Modify: `项目文档/阶段状态.md`
- Modify: `项目文档/文档变更记录.md`

- [ ] **Step 1: 写私信生命周期失败测试**

```python
def test_privacy_export_contains_only_requesters_direct_message_records(client):
    owner, other, conversation_id = _conversation_with_two_users(client)
    _send_message(client, owner, conversation_id, "导出用合成正文", "export-1")
    artifact = _create_and_download_privacy_export(client, owner)
    assert artifact["community"]["direct_messages"][0]["body"] == "导出用合成正文"
    assert "ciphertext" not in artifact["community"]["direct_messages"][0]

def test_account_deletion_removes_direct_message_rows(client):
    owner, _, _ = _conversation_with_two_users(client)
    _complete_deletion_request(client, owner)
    assert _direct_rows_for_user(client, owner["user_id"]) == 0
```

- [ ] **Step 2: 确认失败并实现最小隐私处理**

Run: `apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_account_privacy.py -q -k direct_message`

Expected: FAIL，当前 artifact 和删除流程未处理私信。

在既有 privacy artifact 的 `community` 段增加仅限请求人参与会话的 `direct_conversations` 与 `direct_messages`；消息项仅导出 `id`、`conversation_id`、`sender_username`、解密 `body`、`sequence`、`created_at`，不导出 encryption fields。删除按依赖顺序处理 direct-message 的 outbox、notification、message、member、空 conversation，并移除删除者 actor/recipient 的 direct-message 通知；不得将正文写入审计 details。

- [ ] **Step 3: 更新文档并提交**

在 `需求追踪矩阵.md` 分项登记 I9 的加密、授权、幂等、通知、导出/删除、Web、SSR、浏览器矩阵、迁移和统一门禁；`阶段状态.md` 分开“本地通过”“远端已推送”“Staging 已部署”“UAT 已验收”，无证据不勾选；更新变更记录。

Run: `apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_account_privacy.py -q -k direct_message`

Expected: PASS。

```powershell
git add apps/api/src/password_detective/modules/account_privacy/service.py apps/api/tests/test_account_privacy.py 项目文档/需求追踪矩阵.md 项目文档/阶段状态.md 项目文档/文档变更记录.md
git commit -m "feat(privacy): govern direct message data"
```

### Task 9: 实现 Web 服务层、资料入口、收件箱和会话页

**Files:**
- Modify: `apps/web/src/services/community.ts`
- Modify: `apps/web/src/router/index.ts`
- Create: `apps/web/src/pages/CommunityMessagesPage.vue`
- Create: `apps/web/src/pages/CommunityConversationPage.vue`
- Modify: `apps/web/src/pages/CommunityProfilePage.vue`
- Create: `apps/web/src/pages/CommunityMessagesPage.test.ts`
- Create: `apps/web/src/pages/CommunityConversationPage.test.ts`

- [ ] **Step 1: 写 SSR 失败测试**

```ts
expect(await renderToString(createSSRApp(CommunityMessagesPage))).toContain("私信收件箱");
expect(await renderToString(createSSRApp(CommunityConversationPage))).toContain("发送消息");
```

mock `vue-router`，详情 route 含 `params: { conversationId: "conversation-1" }`；mock `community.ts` 为空分页；复用 `CommunitySearchPage.test.ts` 的 SSR 方式。

- [ ] **Step 2: 确认失败，扩展 API 客户端**

Run: `pnpm --filter @password-detective/web test -- CommunityMessagesPage.test.ts CommunityConversationPage.test.ts`

Expected: FAIL，页面不存在。

实现 `createCommunityDirectConversation`、`listCommunityDirectConversations`、`listCommunityDirectMessages`、`sendCommunityDirectMessage`、`updateCommunityDirectReadState`、`updateCommunityDirectMemberState`。所有函数使用 `apiRequest`、`encodeURIComponent`、现有 header 模式和从 `@password-detective/api-contract` 导入的明确类型。将 `CommunityIdempotencyAction` 加入 `direct-conversation`、`direct-message`、`direct-read-state`、`direct-member-state`，禁用 `any`。

- [ ] **Step 3: 实现受保护页面和资料入口**

收件箱在 `onMounted` 拉取会话、显示安全空态、`RouterLink` 打开会话、`Button` 完成归档/恢复/静音；会话详情加载 cursor 消息，进入时 PATCH 最大 sequence 为已读，使用 Shadcn `Textarea`（label `消息内容`）和 `Button`（`发送消息`）发送并禁用重提。

仅使用 Shadcn `Button`、`Textarea`、`Alert`、`Badge`、`Card` 和 Tailwind utilities：没有 `<style>`、inline style、硬编码 hex 或原生基础按钮/输入。

在 `router/index.ts` 增加：

```ts
{ path: "/community/messages", component: CommunityMessagesPage, meta: { requiresAuth: true } },
{ path: "/community/messages/:conversationId", component: CommunityConversationPage, meta: { requiresAuth: true } },
```

资料页仅对已登录、非本人、无 block 的资料显示 `Button` “发送私信”；成功后 `router.push(`/community/messages/${conversation.id}`)`，失败使用已有 Alert 模式。

- [ ] **Step 4: 验证并提交**

Run: `pnpm --filter @password-detective/web test -- CommunityMessagesPage.test.ts CommunityConversationPage.test.ts && pnpm --filter @password-detective/web typecheck && pnpm --filter @password-detective/web lint`

Expected: PASS，无 `any`、自定义 CSS 或非 Shadcn 基础控件。

```powershell
git add apps/web/src/services/community.ts apps/web/src/router/index.ts apps/web/src/pages/CommunityMessagesPage.vue apps/web/src/pages/CommunityConversationPage.vue apps/web/src/pages/CommunityProfilePage.vue apps/web/src/pages/CommunityMessagesPage.test.ts apps/web/src/pages/CommunityConversationPage.test.ts
git commit -m "feat(web): add community direct message inbox"
```


### Task 10: 覆盖 Chromium、Firefox、WebKit 私信旅程

**Files:**
- Create: `tests/e2e/web-community-messages.spec.ts`
- Modify: `tests/e2e/support/seed_data.ts`（仅当现有种子缺少第二合成用户）

- [ ] **Step 1: 写 Chromium 失败 E2E**

```ts
test("Web 用户可从资料页创建一对一私信并阅读、静音和归档", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  await loginSeededWeb(page);
  await page.goto("/community/users/e2e_dm_recipient");
  await page.getByRole("button", { name: "发送私信" }).click();
  await expect(page).toHaveURL(/\\/community\\/messages\\/[^/]+$/u);
  await page.getByLabel("消息内容").fill("这是端到端验证使用的合成私信。");
  await page.getByRole("button", { name: "发送消息" }).click();
  await expect(page.getByText("这是端到端验证使用的合成私信。", { exact: true })).toBeVisible();
  expectNoBrowserErrors(browserErrors);
});
```

另加 API setup 让第二 seeded 用户发送消息，断言收件箱“未读 1”、打开后“未读 0”，静音/归档仅影响当前账户。所有内容为合成数据。

- [ ] **Step 2: 运行 Chromium 并修正选择器**

Run: `pnpm exec playwright test tests/e2e/web-community-messages.spec.ts --project=web-chromium`

Expected: 实现前 FAIL；实现后 PASS 且没有 pageerror/console error。

- [ ] **Step 3: 运行 Firefox 和 WebKit**

Run: `pnpm exec playwright test tests/e2e/web-community-messages.spec.ts --project=web-firefox; pnpm exec playwright test tests/e2e/web-community-messages.spec.ts --project=web-webkit`

Expected: 两个项目 PASS；记录每浏览器测试数、错误数和重试数。

- [ ] **Step 4: 提交浏览器回归**

```powershell
git add tests/e2e/web-community-messages.spec.ts tests/e2e/support/seed_data.ts
git commit -m "test(web): cover direct message journeys"
```

如果 `seed_data.ts` 不存在或没有改动，只暂存实际变更文件。

### Task 11: 完整门禁、文档收口与部署边界

**Files:**
- Modify: `项目文档/需求追踪矩阵.md`
- Modify: `项目文档/阶段状态.md`
- Modify: `项目文档/文档变更记录.md`
- Modify: `docs/superpowers/specs/2026-08-16-wp5-i9-async-private-messaging-design.md`（仅契约精化必要时）

- [ ] **Step 1: 运行迁移和定向 API 测试**

```powershell
apps/api/.venv/Scripts/python.exe -m alembic -c apps/api/alembic.ini upgrade head
apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_direct_message_crypto.py apps/api/tests/test_community_direct_messages.py apps/api/tests/test_account_privacy.py apps/api/tests/test_migration_0044_direct_messages.py -q
```

Expected: PASS，数据库 migration head 为 `20260816_0044`。

- [ ] **Step 2: 运行前端和跨浏览器门禁**

```powershell
pnpm --filter @password-detective/api-contract typecheck
pnpm --filter @password-detective/web test
pnpm --filter @password-detective/web lint
pnpm --filter @password-detective/web typecheck
pnpm exec playwright test tests/e2e/web-community-messages.spec.ts --project=web-chromium --project=web-firefox --project=web-webkit
```

Expected: PASS；若种子服务或浏览器环境不可用，记录“未验证”及阻塞原因，不能写成通过。

- [ ] **Step 3: 运行项目统一门禁**

Run: `pwsh ./scripts/check.ps1 -SkipInstall`

Expected: PASS。若存在非 I9 遗留失败，记录完整命令、失败文件、当前 commit，在 `阶段状态.md` 标为阻塞项而不是掩盖。

- [ ] **Step 4: 复核文档的证据状态**

将需求追踪矩阵逐项对应本计划：范围、授权/策略/拉黑、AES-GCM keyring、幂等/限流、最小通知、导出/删除、页面、SSR、三浏览器、迁移、统一门禁。没有完成真实 `git push`、远端 ref/tree/commit 比对、服务器 migration/重启/HTTP 检查和 UAT 前，不能把远端、Staging 或生产部署标为完成。

- [ ] **Step 5: 无空白错误审查并提交文档证据**

```powershell
git diff --check
git status --short
git log --oneline --decorate -12
git add 项目文档/需求追踪矩阵.md 项目文档/阶段状态.md 项目文档/文档变更记录.md docs/superpowers/specs/2026-08-16-wp5-i9-async-private-messaging-design.md
git commit -m "docs(community): record direct message verification"
```

Expected: 无 whitespace error，只含 I9 预期变更。用户明确要求推送/部署后，才依次执行 push、远端等价 tree 验证、目标服务器迁移、重启、健康检查和私信 UAT；本地 build 或压缩包不能构成部署证明。

## 最终验收清单

- [ ] 会话只能由两个活动、未互相拉黑、满足接收方策略的不同用户建立，canonical pair 不会重复。
- [ ] 正文仅以独立 keyring 的 AES-GCM ciphertext/nonce/version 存储，API 仅向成员解密；错误/通知不泄露正文。
- [ ] 写操作有 `Idempotency-Key`、安全回放、key-payload conflict 409 和限流。
- [ ] cursor 无重复遗漏；读取状态仅向前；归档/静音只影响本人。
- [ ] 新私信通知为最小摘要；拉黑、偏好关闭、静音无可见即时投递。
- [ ] 导出/删除处理私信数据，删除后不保留其他成员可读副本。
- [ ] Web 页面移动优先，Shadcn-Vue/Tailwind，无自定义 CSS，含 SSR 测试。
- [ ] Chromium、Firefox、WebKit E2E 无浏览器错误。
- [ ] `pwsh ./scripts/check.ps1 -SkipInstall` 通过，migration head 为 `20260816_0044`，文档只陈述真实验证证据。
