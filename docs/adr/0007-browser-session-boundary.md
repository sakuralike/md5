# ADR-0007：浏览器会话与桌面令牌边界

- 状态：已接受
- 日期：2026-08-02
- 对应需求：AUTH-02、AUTH-03、AUTH-04

## 背景

Web、管理端和 Windows 桌面端使用同一认证服务，但浏览器长期令牌暴露给 JavaScript 会扩大 XSS 后的会话劫持范围；桌面端则不能依赖浏览器 Cookie。管理端还需要与用户端隔离，并强制 TOTP。

## 决策

1. Windows 桌面端和受信 API 客户端继续使用 JSON 形式的访问令牌与刷新令牌，并执行刷新轮换和重放检测。
2. 用户 Web 与管理端使用专用浏览器认证端点。刷新令牌只写入 `HttpOnly`、`SameSite=Lax` Cookie，不出现在 JSON 响应或浏览器存储中。
3. 用户端与管理端分别使用 `pd_web_refresh` 和 `pd_admin_refresh`，Cookie Path 分别限制到各自的认证端点，避免两个入口互相携带长期凭据。
4. 浏览器请求校验 `Origin` 是否在明确的 CORS 白名单中；生产环境必须启用 `Secure` Cookie 并使用 HTTPS。
5. 浏览器仅在 `sessionStorage` 暂存短期访问令牌和最小用户摘要；关闭标签页后清除。后续可升级为纯 BFF 会话以进一步降低 JavaScript 可见令牌范围。
6. 管理端登录只允许 `moderator` 或 `admin`，且访问管理功能前必须已配置 TOTP，并在本次登录中完成 TOTP 验证。
7. 浏览器登出以受限路径的刷新 Cookie 为撤销依据，即使访问令牌已过期也能撤销会话族并清除 Cookie。

## 后果

- Web/Admin 与桌面端拥有清晰的会话传输边界，同时复用同一会话族与审计模型。
- Cookie 模式要求正确配置 HTTPS、CORS、反向代理和来源白名单。
- 短期访问令牌仍对同一标签页中的脚本可见，因此内容安全策略、依赖治理和未来 BFF 迁移仍是后续安全工作。
