# MD5桌面端

> 状态：历史需求参考，不作为当前开发基线。若与 v3.0 规格冲突，以当前规格说明书为准。

> 原始来源：`MD5桌面端.docx`

一、桌面端功能修改（基于C#）

将原有的Electron（JavaScript/TypeScript）桌面端改为基于C#的桌面应用程序，推荐使用 Windows Forms (WinForms) 或 Windows Presentation Foundation (WPF) 框架。核心功能与交互逻辑保持不变，但实现技术和API调用方式将发生变化。

1. 核心功能实现说明

本地哈希计算：使用 System.Security.Cryptography 命名空间下的 MD5、SHA1、SHA256、SHA512 类进行哈希计算。支持输入文本字符串或选择文件（通过 OpenFileDialog）进行计算。

加密压缩包处理：

使用第三方库（如 SharpCompress 或 SevenZipSharp）处理 .zip、.rar、.7z 等格式的加密压缩包。

用户通过界面选择压缩包并输入密码后，程序调用库函数进行解密。

解密成功后，遍历压缩包内的文件列表，对每个文件内容进行哈希计算（使用上述 System.Security.Cryptography 类）。

将解压出的密码（明文）与计算出的每个文件的哈希值在界面中展示给用户。

提交到平台：使用 System.Net.Http.HttpClient 类发送HTTP请求到后端API。请求头中需携带固定的程序标识，用于后端识别为桌面端提交。

2. 程序标识与防篡改（简化版）

标识方式：

User-Agent：固定为 DeepPwdDesktop/2.0 (Windows; C#)。

X-Device-ID：程序启动时，通过 SystemInfo 或 ManagementObjectSearcher 获取本机硬件信息（如主板序列号、MAC地址）的哈希值作为设备ID。此ID用于后端统计，但不用于强身份验证。

防篡改策略：遵循文档中的简化方案。后端不对 User-Agent 和 X-Device-ID 进行强校验。即使攻击者伪造了请求头，由于无法模拟完整的程序行为（如本地解密逻辑），后端也只会将其标记为 source='web' 并赋予 status='pending'，不会获得桌面端提交的 preliminary 初始状态。

3. 界面设计与技术选型

框架：推荐使用 WPF，其XAML界面设计能力更强，更容易实现文档中描述的二次元风格和毛玻璃效果。

UI组件：

使用 Material Design in XAML Toolkit 或 MahApps.Metro 等开源UI库来快速实现现代化、美观的界面。

对于加密压缩包处理界面，直接使用WPF原生控件（如 TextBox、Button、ListView/DataGrid）即可实现。

交互逻辑：所有耗时操作（如文件哈希计算、压缩包解密、网络请求）都应在异步线程（async/await）中执行，避免阻塞UI线程，保持界面响应流畅。

二、适配C#桌面端的后端API接口调整

为支持C#桌面端的提交，后端API接口需要做如下调整和明确：

1. 桌面端专用提交接口

接口路径：POST /api/tool/submit （与原有路径一致，但请求参数和校验逻辑需明确）

请求头要求：

Content-Type: application/json

Authorization: Bearer <JWT_TOKEN> （用户需先登录获取Token）

User-Agent: DeepPwdDesktop/2.0 (Windows; C#) （程序标识）

X-Device-ID: <设备硬件哈希> （可选，用于统计）

请求体 (JSON)：

on
{
"hash_type": "MD5", // 枚举值: MD5, SHA1, SHA256, SHA512
"hash_value": "482c811da5d5b4bc6d497ffa98491e38",
"plaintext": "password123",
"filenames": "readme.txt,secret.png" // 可选，压缩包内文件列表，逗号分隔
}

* **后端处理逻辑**：

1. **身份验证**：验证JWT Token，获取提交者 `user_id`。

2. **来源识别**：检查请求头 `User-Agent`。如果其值匹配 `DeepPwdDesktop/2.0*` 模式，则判定为桌面端提交，`source='desktop'`；否则，判定为网页端提交，`source='web'`。

3. **数据校验**：对 `plaintext` 计算 `hash_type` 对应的哈希值，并与 `hash_value` 比对。不一致则返回错误。

4. **去重检查**：在 `hash_records` 表中查询 `hash_type` 和 `hash_value` 是否已存在。若存在，返回提示信息。

5. **状态设置**：

* 若来源为 `desktop`，则初始状态设为 `status='preliminary'`。

* 若来源为 `web`，则初始状态设为 `status='pending'`。

6. **写入数据库**：将数据（包含 `filenames` 字段）插入 `hash_records` 表。同时，向 `contribution_log` 表插入一条记录，`source` 字段根据实际来源填写。

7. **返回响应**：返回提交成功或失败的JSON。

#### 2. 正向查询接口调整

* **接口路径**：`GET /api/search/hash-to-plain`

* **响应体调整**：在原有的响应数据中，增加 `filenames` 字段。如果该条哈希记录对应的 `filenames` 字段不为空，则返回该值；否则，不返回或返回 `null`。

```js

on

{

"success": true,

"data": {

"plaintext": "password123",

"verify_count": 5,

"status": "verified",

"filenames": "readme.txt,secret.png" // 新增字段

}

}
```

3. 用户认证接口（无变化）

登录接口：POST /api/auth/login。C#桌面端使用 HttpClient 发送包含用户名和密码的JSON请求，获取JWT Token。

注册接口：POST /api/auth/register。功能同上。

4. 贡献与验证接口（无变化）

确认接口：POST /api/contribute/confirm。用于其他用户对某条数据进行社区确认。

查询贡献记录：GET /api/contribute/my-records。用于桌面端用户查看自己的提交历史和积分获取情况。

总结

通过以上修改，原Electron桌面端被完整迁移至C#平台。后端API的调整主要集中在来源识别和数据字段扩展上，确保了C#桌面端提交的数据能被正确标记和优先处理，同时保持了后端
