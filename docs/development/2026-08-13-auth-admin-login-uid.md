# 2026-08-13 认证、管理员准入与 UID 开发记录

## 本轮目标

1. 用户端和管理端支持用户名或邮箱加密码登录。
2. 管理员账号默认不启用 TOTP，但保留可选增强验证。
3. 登录页增加安全的记住账号能力。
4. 对外响应和界面展示稳定 UID。
5. 管理后台可按用户名、邮箱或 UID 查询用户。
6. 测试通过后同步远端并部署目标服务器。

## 安全决策

- **不保存密码**：记住登录仅保存修剪后的用户名或邮箱。密码输入仍使用 `autocomplete="current-password"`，由浏览器密码管理器自行决定是否保存。
- **TOTP 可选但不降级已启用账号**：未启用 TOTP 时管理员使用密码登录和再认证；一旦启用，登录令牌与管理端准入必须包含 MFA 验证状态，敏感操作也必须再次提交有效动态码。
- **UID 定义**：当前 UID 与用户 UUID 主键一致，避免新增可枚举数字标识和数据库迁移；API 同时返回 `id` 和 `uid`，前端兼容旧响应时回退到 `id`。
- **管理员凭据不入库**：部署账号由一次性脚本从临时受限文件读取，脚本执行后删除文件并撤销旧会话。

## 接口与界面变化

- `UserResponse`、`AdminUserListItem` 和 `AdminUserDetail` 新增 `uid`。
- `AdminReauthenticationRequest.totp_code` 改为可选；账号已启用 TOTP 时服务层仍强制校验。
- `/api/v1/admin/access-check` 返回真实 MFA 状态：`verified` 或 `not_verified`。
- Web `/login`、Admin `/login` 增加记住登录账号复选框与不保存密码提示。
- Web `/user-center` 展示 UID；Admin 用户治理列表、详情展示 UID，搜索提示改为用户名、邮箱或 UID。

## 验收命令

```powershell
apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_auth.py apps/api/tests/test_n2_admin_users.py -q
pnpm --filter @password-detective/web typecheck
pnpm --filter @password-detective/admin typecheck
pnpm --filter @password-detective/web lint
pnpm --filter @password-detective/admin lint
pnpm --filter @password-detective/web test -- --run
pnpm --filter @password-detective/admin test -- --run
pnpm --filter @password-detective/web build
pnpm --filter @password-detective/admin build
```
