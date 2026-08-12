# 2026-08-12 HTTP 非安全上下文请求标识兼容修复

## 背景

生产测试服务器当前直接通过 HTTP IP 地址提供 Web 与管理端页面。浏览器在非安全上下文中可能暴露 `crypto`，但不提供 `crypto.randomUUID()`；此前注册请求会在生成 `X-Request-ID` 时中断并显示 `crypto.randomUUID is not a function`。

## 实现

- Web 与 Admin 分别新增 `lib/clientId.ts`，统一提供请求标识生成。
- 优先使用原生 `crypto.randomUUID()`。
- 原生 UUID 不可用时，使用 `crypto.getRandomValues()` 生成符合 RFC 4122 v4 位布局的 UUID。
- 极旧浏览器连 Web Crypto 都不可用时，使用时间戳与进程内序列生成非安全、但满足请求追踪与幂等唯一性需要的兜底标识。
- 替换 Web 注册、登录、账号、社区、信任工单，以及 Admin 用户治理、系统设置、社区治理、风险告警等全部直接 `crypto.randomUUID()` 调用，防止其他写操作出现同类错误。

## 安全边界

这些标识只用于请求追踪与幂等去重，不作为认证令牌、密码学随机数、密钥或访问凭据。认证和加密所需随机性仍必须由服务端安全随机源提供。

## 验证

- Web ESLint、TypeScript、Vitest。
- Admin ESLint、TypeScript、Vitest。
- 新增三种运行环境测试：原生 UUID、仅 `getRandomValues`、无 Web Crypto。
- 部署后通过 HTTP 目标环境执行注册请求与管理端访问回归。
