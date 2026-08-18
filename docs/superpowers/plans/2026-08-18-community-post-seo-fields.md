# 社区帖子 SEO 字段实施计划

> **For agentic workers:** 本计划在当前隔离 worktree 内执行；每个任务完成后运行对应验证，并在本轮完成统一门禁、SSH 推送和 Staging 复核。

**Goal:** 为社区帖子增加安全、可审计、支持幂等与乐观并发的内容级 SEO 字段写入能力，并接入现有受控 `seo` 投影。

**Architecture:** 在 `CommunityPost` 上增加可空 SEO 字段和独立版本号；通过独立 `PATCH /api/v1/community/posts/{post_id}/seo` 写入，复用帖子作者可见性约束、群组治理权限和现有幂等机制。服务端统一进行字段归一化和安全校验，公开详情继续只返回通过资格矩阵后的投影；旧数据全部走内容标题/摘要/canonical 回退，不因迁移自动变为可索引。

**Tech Stack:** FastAPI、Pydantic、SQLAlchemy 2、Alembic、pytest、pnpm TypeScript API contract、现有审计与 Idempotency-Key 基础设施。

---

### Task 1: 固定数据模型、合同和安全归一化边界

**Files:**
- Create: `apps/api/alembic/versions/20260818_0048_community_post_seo_fields.py`
- Modify: `apps/api/src/password_detective/db/models/community.py`
- Modify: `apps/api/src/password_detective/modules/community/schemas.py`
- Modify: `packages/api-contract/src/index.ts`
- Test: `apps/api/tests/test_community_post_seo.py`

- [ ] **Step 1: Write failing tests for model contract and validation**
  - 覆盖空值回退、标题 120 Unicode 字符、描述 320 Unicode 字符、最多 20 个关键词、关键词总长度、控制字符、HTML/脚本协议、外部 canonical、带凭据 OG 图片均被拒绝。
  - 覆盖 `CommunityPostDetail.seo` 在旧数据空字段下继续使用既有标题/摘要/canonical。
- [ ] **Step 2: Run the focused test to verify the intended failure**

```powershell
cd apps/api
& .\.venv\Scripts\python.exe -m pytest tests/test_community_post_seo.py -q
```

Expected: FAIL because the SEO write schema, model columns, and migration are not present.
- [ ] **Step 3: Add nullable SQLAlchemy fields**
  - `seo_title`、`seo_description`、`seo_keywords` JSON、`seo_canonical_path`、`og_image_url` 均允许 NULL。
  - 增加 `seo_version`，默认 1，作为 SEO 独立乐观并发版本；不改变帖子正文 `version`。
- [ ] **Step 4: Add Pydantic request/response contracts**
  - 请求使用可选字段，显式传 `null` 表示清除；未提供字段表示保持原值。
  - 响应返回当前 SEO 字段和 `seo_version`，不返回数据库内部审计字段。
- [ ] **Step 5: Add Alembic upgrade/downgrade**
  - 升级添加可空字段、默认 `seo_version=1`。
  - 降级删除新增字段；不得截断已有内容或将旧内容变成可索引。
- [ ] **Step 6: Run focused tests and migration head check**

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/test_community_post_seo.py -q
& .\.venv\Scripts\python.exe -m alembic heads
```

Expected: focused tests pass and exactly one migration head remains.

### Task 2: Implement server-side normalization and controlled projection

**Files:**
- Modify: `apps/api/src/password_detective/modules/community/seo_projection.py`
- Modify: `apps/api/src/password_detective/modules/community/service.py`
- Modify: `apps/api/src/password_detective/modules/community/schemas.py`
- Test: `apps/api/tests/test_community_seo_projection.py`

- [ ] **Step 1: Add failing projection tests**
  - 有自定义标题/描述/关键词/canonical/OG 图片时返回清洗后的值。
  - 空字段回退到帖子标题、公开摘要和服务端生成 canonical。
  - 帖子不具备公开资格时所有内容级字段仍为空。
- [ ] **Step 2: Run projection tests and confirm failure**

```powershell
cd apps/api
& .\.venv\Scripts\python.exe -m pytest tests/test_community_seo_projection.py -q
```

Expected: FAIL because the projection does not yet read persisted fields.
- [ ] **Step 3: Implement pure normalization helpers**
  - trim、控制字符拒绝、长度限制、关键词去重/去空、HTML/模板表达式拒绝。
  - canonical 只允许站内绝对路径格式，不信任请求 Host。
  - OG 图片仅允许受信配置 Origin 的 HTTPS URL或明确批准的相对资源，并拒绝用户名、密码、签名参数。
- [ ] **Step 4: Wire normalized fields into `post_seo_projection`**
  - 保留已有资格矩阵和 `indexable=false`。
  - 自定义字段只覆盖对应回退值，不改变公开资格判定。
- [ ] **Step 5: Run projection and community regression tests**

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/test_community_seo_projection.py tests/test_community.py tests/test_community_groups.py tests/test_community_profiles.py -q
```

### Task 3: Add authorized PATCH write service with idempotency and audit

**Files:**
- Create: `apps/api/src/password_detective/modules/community/seo_service.py`
- Modify: `apps/api/src/password_detective/modules/community/router.py`
- Modify: `apps/api/src/password_detective/modules/community/service.py`
- Test: `apps/api/tests/test_community_post_seo.py`

- [ ] **Step 1: Write failing API tests**
  - 作者可以更新自己的帖子 SEO。
  - 非作者、非群组治理成员不能修改；管理员按现有社区管理员权限可修改。
  - 帖子不可见或已删除时不泄露资源存在性。
  - `If-Match`/请求体 `expected_seo_version` 不匹配返回 409。
  - 重复 `Idempotency-Key` 返回同一响应且不重复写审计。
  - 成功写入生成审计摘要，不记录完整描述、外部 URL 或任何敏感值。
- [ ] **Step 2: Run API tests to verify failure**

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/test_community_post_seo.py -q
```

Expected: FAIL because the route and service are absent.
- [ ] **Step 3: Implement authorization and mutation service**
  - 作者沿用帖子可见性和作者校验。
  - 群组治理成员沿用 `_require_group_governor`；管理员沿用现有 `UserRole.MODERATOR/ADMIN` 判断。
  - 使用现有 `_mutate_with_idempotency`，scope 固定为 `community.post.seo.update`。
  - 成功时只递增 `seo_version`，写入审计 action `community.post.seo.update`，并返回详情。
- [ ] **Step 4: Add route and contract export**
  - `PATCH /api/v1/community/posts/{post_id}/seo`。
  - 强制 `Idempotency-Key`，使用 `If-Match` 或请求体版本字段之一；缺失返回 428/422，冲突返回 409。
- [ ] **Step 5: Run focused tests and contract typecheck**

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/test_community_post_seo.py -q
pnpm --filter @password-detective/api-contract typecheck
```

### Task 4: Add frontend/API contract coverage without introducing a new workbench

**Files:**
- Modify: `packages/api-contract/src/index.ts`
- Modify: `apps/web/src/lib/communityAvatar.test.ts` only if shared contract fixtures require it
- Test: existing API contract tests or `apps/api/tests/test_community_post_seo.py`

- [ ] **Step 1: Confirm no UI requirement is added in this slice**
  - 本轮不新增页面、不新增原生表单控件、不改变现有社区交互。
- [ ] **Step 2: Verify generated/handwritten contract fixtures**
  - 确认 `seo_version`、可空字段和 PATCH 响应在 TypeScript 中与 Pydantic 一致。
- [ ] **Step 3: Run Admin/Web typecheck and existing tests**

```powershell
pnpm --filter @password-detective/admin typecheck
pnpm --filter @password-detective/web typecheck
pnpm --filter @password-detective/web test -- --run
```

### Task 5: Unified gate, documentation, SSH delivery and Staging verification

**Files:**
- Modify: `项目文档/实施计划/SEO内容级字段与SSR实施计划.md`
- Modify: `docs/testing/requirements-traceability.md`
- Modify: `项目文档/文档变更记录.md`

- [ ] **Step 1: Run unified local gates**

```powershell
pnpm typecheck
pnpm lint
pnpm test
pnpm build
```

- [ ] **Step 2: Update traceability and change log**
  - 记录 Task 7-B 本轮只完成帖子 SEO 字段切片，群组/用户字段仍待后续切片。
  - 记录迁移、权限、幂等、并发、XSS/URL 校验和旧数据回退证据。
- [ ] **Step 3: Commit only intended files and push through SSH**
  - 使用 `git push ssh-release HEAD:refs/heads/codex/seo-settings-plan`。
  - 验证远端 ref 与本地提交一致。
- [ ] **Step 4: Build and deploy Staging from verified archive**
  - 先校验归档 SHA-256，再构建 API 镜像，使用 API HA overlay，保持 API=2、Worker=3。
  - 不使用 `--remove-orphans`，不删除监控、数据库或缓存容器。
- [ ] **Step 5: Verify target environment**
  - Alembic head、目标 API schema import、API ready、社区 SEO PATCH 权限/冲突/幂等 smoke、Web/Admin 200、robots/sitemap 安全默认、Nginx 配置测试。
  - 不以本地测试替代 Staging 证据；不宣称 SSR 或生产放行。

---

## Scope boundary

本计划不实现群组/用户 SEO 字段、动态 sitemap、SSR/预渲染、百度推送、SEO 版本历史、发布/回滚或独立管理工作台。下一轮可复用本轮字段归一化和授权模式扩展到群组与用户资料。
