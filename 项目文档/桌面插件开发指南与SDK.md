# 桌面插件开发指南与 SDK

本文档面向密码侦探社桌面端 PDPP v1 插件开发者。插件以独立进程运行，通过 JSON-RPC 2.0 over stdio 与宿主通信；插件不能加载到宿主进程，也不能注入 XAML、HTML、脚本或任意 WPF 对象。

## 目录结构

```text
plugins/my-plugin/
  manifest.json
  schemas/command.schema.json
  bin/windows-x64/plugin.exe
  sbom.cdx.json
```

清单必须声明 `schema=pd.plugin/v1`、反向域名式 `plugin_id`、严格 SemVer、入口程序、命令、权限和资源限制。命令 Schema 只能使用 `object`、`string`、`integer`、`number`、`boolean`；文件字段使用 `format=file`，皮肤背景使用 `format=theme-background`。

## 生命周期与权限

宿主发送 `initialize`、`health/check`，运行时发送 `command/execute`，关闭时发送 `shutdown`。每条消息都是单行 JSON-RPC 2.0，插件必须返回相同 `id`。`ui:command` 展示命令表单；`ui:theme` 调用主题 Broker；`file:read:selected` 只允许读取用户明确授权的文件；`storage:private` 提供插件私有存储。权限按清单申请、平台批准和用户授予的交集生效。

宿主 Broker v1 接口：

| 方法 | 所需权限 | 用途 |
| --- | --- | --- |
| `host/file/read` | `file:read:selected` | 按不透明 `file_ref` 分块读取用户明确选择的文件，单块最多 512 KiB |
| `host/file/digest` | `file:read:selected` | 对已授权文件计算 `md5`、`sha1`、`sha256` 或 `sha512` |
| `host/storage/get` | `storage:private` | 读取插件私有 JSON 值 |
| `host/storage/set` | `storage:private` | 原子写入插件私有 JSON 值 |
| `host/storage/remove` | `storage:private` | 删除插件私有 JSON 值 |
| `host/api/profile/read` | `api:profile:read` | 通过宿主代理读取当前账号聚合资料 |
| `host/api/hash/read` | `api:hash:read` | 通过宿主代理查询授权哈希摘要 |
| `host/api/verification/submit` | `api:verification:submit` | 通过宿主代理提交一次性验证回执 |
| `host/ui/theme/apply` | `ui:theme` | 应用宿主支持的受控主题 |

Broker 不提供目录枚举、任意文件写入、凭据读取、后台常驻、子进程派生或任意网络请求。文件引用只在当前命令会话内有效，插件不得把原始文件路径或授权令牌写入输出。

## 主题 Broker

调用 `host/ui/theme/apply` 时提交：

```json
{"preset":"forest","background_ref":"32 位引用","background_opacity":0.8,"clear_background":false}
```

预设为 `light`、`dark`、`forest`、`contrast`。背景图片由 `theme-background` 字段触发宿主文件选择器，宿主只接受 PNG/JPG/JPEG 且不超过 10 MB，复制后返回不透明引用。插件不会获得原始路径；宿主负责渲染、持久化和恢复主题。

## C# SDK

引用 `packages/pdpp-sdk-dotnet/PasswordDetective.Pdpp.Sdk.csproj` 并继承 `PdppPlugin`：

```csharp
internal sealed class SkinPlugin : PdppPlugin
{
    public SkinPlugin() : base("com.example.skin", "1.0.0", ["ui:command", "ui:theme"]) { }

    protected override async Task<object> ExecuteAsync(
        string command, JsonElement input, PdppHostClient host, CancellationToken cancellationToken)
    {
        var result = await host.ApplyThemeAsync(
            input.GetProperty("preset").GetString()!, null, 1, false, false, cancellationToken);
        return new { applied = result.GetProperty("applied").GetBoolean() };
    }
}
```

SDK 提供 `RunAsync`、健康检查、优雅关闭、结构化错误和 `PdppHostClient.CallAsync`。Broker 错误会以 `PdppHostException` 抛出并保留错误码。文件类插件可使用 `PluginSelectedFile.FromJson`、`ReadFileAsync`、`ReadFileToEndAsync` 和 `DigestFileAsync`；状态型插件可使用 `GetStorageAsync`、`SetStorageAsync`、`RemoveStorageAsync`；需要平台数据时使用 `ReadProfileAsync`、`ReadHashAsync` 和 `SubmitVerificationAsync`。

### 官方插件包体检工具

`plugins/official-plugin-inspector` 是首个使用文件 Broker 扩展的官方插件。它提供 `inspect` 命令，要求用户明确选择一个 `.pdpkg` 文件，返回结构化 JSON 报告：包大小和 SHA-256、ZIP 文件项数量与展开大小、路径安全、Manifest 字段/版本/入口/命令 Schema/权限/资源限制、CycloneDX 1.5 SBOM、开发者 Ed25519 签名、源码 UTF-8/数量/大小，以及 `passed`、`warning` 或 `failed` 状态。插件最多读取 128 MiB，源码最多检查 32 个文件且单文件最多 256 KiB；不会上传包内容、用户路径或密钥。

使用与其他官方插件相同的环境变量构建：

```powershell
$env:PDPP_PUBLISHER_KEY_ID = "official-plugin-inspector-key"
$env:PDPP_PUBLISHER_PRIVATE_KEY_BASE64 = "<secure-build-secret>"
pwsh ./plugins/official-plugin-inspector/build-package.ps1
```

打包器会按 Manifest 中声明的全部命令复制 `schemas/`，递归复制 `assets/`，并把插件源文件放入 `source/`；这样多命令和多文件官方插件可以复用同一构建流程。

## 签名、SBOM 与打包

`.pdpkg` 必须包含逐文件 SHA-256、开发者 Ed25519 签名和 CycloneDX 1.5 SBOM。私钥只能从安全构建环境注入。官方皮肤示例位于 `plugins/official-skin`：

平台发布签章支持自建 OpenBao Transit。部署 `infra/openbao/config.hcl` 后运行 `infra/openbao/init-transit.sh` 创建不可导出的 Ed25519 Transit 密钥；API 仅持有受限 Transit Token，通过 `/v1/transit/sign/<key>` 请求签名，不读取私钥。生产环境应将 OpenBao 数据目录单独备份并启用 TLS 或内网 mTLS。

后端配置项：

| 环境变量 | 必填 | 说明 |
| --- | --- | --- |
| `DESKTOP_PLUGIN_SIGNING_BACKEND` | 是 | `openbao_transit` 启用 Transit；`derived` 仅用于本地开发。 |
| `DESKTOP_PLUGIN_SIGNING_URL` | 是 | API 容器访问的 OpenBao 地址，例如 `http://openbao:8200`。 |
| `DESKTOP_PLUGIN_SIGNING_TOKEN_FILE` | 是 | 指向 Docker Secret 文件；Token 只授予目标 Transit key 的 `sign` 和 `read`。 |
| `DESKTOP_PLUGIN_SIGNING_KEY` | 是 | Transit 密钥名，默认 `password-detective-plugin-platform`。 |

LLM 审核配置：

| 环境变量 | 说明 |
| --- | --- |
| 模型协议/API 地址/模型名称 | 在插件商城管理的审核策略中保存。 |
| `DESKTOP_PLUGIN_LLM_REVIEW_API_KEY_FILE` | Docker Secret 文件路径；不得使用管理端表单保存密钥。 |
| `DESKTOP_PLUGIN_LLM_REVIEW_TIMEOUT_SECONDS` | 调用超时，默认 30 秒。 |

默认关闭大模型审核和 Windows 动态审核；默认路径仅执行静态规则并进入管理员人工审核。两种自动审核均可由管理员单独启用。LLM 只读取清单、能力、SBOM/静态审核摘要和制品摘要；不上传二进制、用户文件、令牌或服务器秘密。LLM 阻断或已配置服务调用失败会失败关闭，绝不自动发布。

DeepSeek 使用 OpenAI 兼容模式：模型协议选择 `openai_compatible`，API 地址填写 `https://api.deepseek.com`，模型填写 `deepseek-chat`。API Key 只从服务器秘密配置读取，管理端不显示、保存或回显该值。

OpenBao 服务建议使用文件存储卷、单独网络、不可导出 Ed25519 key、短期周期 Token 和审计设备。不要把 root token、解封密钥或签名 Token 写入 Git、普通 API 日志或镜像层。管理员插件审核、批准、发布、下架、撤销和策略管理均要求管理员 MFA；Runner 注册和撤销额外要求纯管理员角色。

开发者可向 `POST /api/v1/developer/plugins/signing-keys` 只提交 `reauth_token`，由服务器生成 Ed25519 密钥对并登记公钥；私钥 Base64 仅在创建响应中返回一次，后续列表和读取接口只返回公钥。开发者必须立即将该私钥保存到本地安全存储，并作为 `PDPP_PUBLISHER_PRIVATE_KEY_BASE64` 传给打包脚本；服务端不保存开发者私钥。

```powershell
$env:PDPP_PUBLISHER_KEY_ID = "official-skin-key"
$env:PDPP_PUBLISHER_PRIVATE_KEY_BASE64 = "<secure-build-secret>"
pwsh ./plugins/official-skin/build-package.ps1
```

## 本地调试与上架

先运行 `dotnet build`，再在本地插件市场浏览 `.pdpkg`。本地包始终显示“未审核”。上架必须经过项目、密钥、版本、隔离上传、finalize、自动审核、Windows 动态审核、管理员批准和 stable 发布；发布后目录还会校验平台签章、撤销列表、架构和制品摘要。

管理员审核详情会显示插件包内 `source/` 下的文本源码（单文件最多 256 KiB，最多 32 个文件）。没有可审源码的版本不能批准；源码仅供管理员只读查看，不能替代静态审核、签名校验和人工安全判断。

## 安全禁止项

禁止路径穿越、目录枚举、未声明网络、进程派生、凭据读取、持久化自启动、秘密硬编码、任意 UI 注入，以及把用户文件路径回传第三方服务。新增权限、签名密钥变化或主版本升级必须重新确认。
