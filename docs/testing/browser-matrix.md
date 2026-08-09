# Web/Admin 浏览器与设备验收矩阵

- 更新日期：2026-08-09
- 当前自动化基线：Playwright Chromium、Firefox、WebKit，每个引擎 Web/Admin 共 30 项旅程
- 结论边界：本地 Windows 的 Playwright Chromium、Firefox、WebKit 预检已验证；远端三浏览器 CI 状态见下表。Playwright WebKit 不等同于真实 Safari，Edge、Safari、操作系统辅助技术和真实设备不能据此标记通过

## 1. 自动化与目标矩阵

| 通道 | 操作系统 | 浏览器 | 视口/设备 | 验收类型 | 当前状态 |
|---|---|---|---|---|---|
| 本地开发 | Windows | Playwright Chromium | 1440 × 900、390 × 844 | 30 项功能、结构视觉、无溢出、Axe | 已通过（2026-08-09） |
| 本地跨引擎 | Windows | Playwright Firefox | 1440 × 900、390 × 844 | 与 Chromium 相同的完整 30 项旅程 | 已通过（2026-08-09） |
| 本地兼容预检 | Windows | Playwright WebKit | 1440 × 900、390 × 844 | 完整 30 项旅程；跳过链接直接聚焦后验证 Enter 激活 | 已通过（2026-08-09）；不替代 Safari Tab 实测 |
| GitHub Actions | `ubuntu-latest` | Chromium、Firefox、WebKit 矩阵 | 测试配置固定视口 | 每个引擎 30 项 E2E，失败制品按浏览器隔离 | 已通过，运行 `31319884808`（三个浏览器矩阵作业） |
| 目标桌面 | Windows 11 | Microsoft Edge Stable | 1440 px、200% 缩放 | 自动化复跑 + 人工视觉/读屏器 | 未验证 |
| 兼容桌面 | Windows 10 | Microsoft Edge Stable | 1366 × 768、200% 缩放 | 核心旅程与布局 | 未验证 |
| Apple Web | macOS | Safari Stable | 桌面与响应式 | 人工功能、首次 Tab、视觉、VoiceOver | 未验证 |
| 移动端网页 | iOS | Safari | 真实 iPhone 或受控设备云 | 触摸、缩放、键盘和安全流程 | 未验证 |
| 移动端网页 | Android | Chrome | 真实 Android 或受控设备云 | 触摸、缩放、键盘和安全流程 | 未验证 |

## 2. 分级准入

### PR/推送必须通过

- Ubuntu CI 的 API、Frontend、Desktop、Container Images 和 Chromium/Firefox/WebKit 三项 E2E 矩阵。
- 三个 Playwright 引擎的完整 30 项核心旅程、页面级无横向溢出、关键区域边界和 Axe 严重/关键违规门禁。
- 失败时上传脱敏后的 Playwright 证据；含密码、TOTP、一次性凭证的场景继续关闭截图或 Trace。

### WP3 外部验收必须补齐

- Windows 11 + Edge 的核心旅程、200% 缩放、NVDA 和人工视觉复核。
- Windows 10 + Edge 的最小兼容抽样。
- macOS + Safari + VoiceOver 的关键安全与治理旅程。
- 至少一组真实 iOS Safari 和 Android Chrome 的移动端布局与表单操作。

### 生产放行前仍需

- 目标域名、TLS、反向代理、Cookie 属性、CSP、真实 MySQL/Redis/Worker/通知环境上的同版本复跑。
- 目标设备、网络条件和浏览器策略下的下载、导出、会话、TOTP、案件处置和风险告警操作。
- 所有 P0/P1 缺陷关闭，或 P1 有书面风险接受、责任人和截止日期。

## 3. 旅程覆盖优先级

| 优先级 | Web | Admin |
|---|---|---|
| P0 | 登录/刷新/退出、查询与揭示、贡献、密码/TOTP/会话、隐私删除 | 登录/TOTP、用户停用恢复、双人角色审批、候选与案件最终处置 |
| P1 | 邮箱验证、举报/申诉、积分信誉、活动记录 | 配置发布回滚、风险告警、审计查询导出 |
| P2 | 次要空态、帮助文案和非阻断视觉差异 | 次要筛选组合和长列表极端数据 |

## 4. 失败与豁免

- 浏览器特有失败必须记录浏览器版本、操作系统、视口、复现步骤和脱敏证据。
- 不允许通过长期跳过 P0 旅程维持绿色；临时隔离必须有责任人、到期日期和替代人工验收。
- 同一 Chromium 结果不能推导 Edge、Firefox、Safari 已通过；WebKit 预检也不能替代真实 Safari。
- CI 自动化通过不代表目标环境、真实邮件、真实设备或生产网络已验收。

## 5. 下一步执行顺序

1. 建立 Edge/Windows 11 目标环境执行记录，完成 NVDA 清单。
2. 安排 macOS Safari 的首次 Tab、关键安全旅程与 VoiceOver 人工验收，不以 WebKit 预检代替。
3. 完成 iOS Safari、Android Chrome 的真实设备抽样。
4. 将通过记录、缺陷和风险接受汇总到 WP3 出口报告。
5. 并行启动 WP4 首批安全扫描与 SBOM，再进入恢复、性能和可观测性准入。
