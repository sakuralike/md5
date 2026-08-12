# 2026-08-12 页面视觉改造记录

## 目标

以 `E:/只比主题/minimax/1.html` 的现代简白视觉为参考，在不复制原始 CSS、不引入额外 UI 库的前提下，统一 Web 与 Admin 的页面外壳和登录入口。

## 实现

- 使用 Tailwind 语义变量定义紫色主色、粉色强调色、浅色背景和更大的圆角尺度。
- Web 保留背景预设和自定义本地背景能力，默认外观改为柔和紫粉光晕、玻璃顶栏和胶囊导航。
- Web `/login` 改为移动端单栏、桌面端双栏；所有字段继续使用 Shadcn-Vue `Input`、`Label`、`Button`、`Card` 和 `Alert`。
- Admin 外壳改为玻璃顶栏和语义色柔光背景；Admin `/login` 与 Web 登录保持同一视觉语言。
- `/community` 首页的主视觉和主要内容卡片改为半透明玻璃层，业务结构与交互保持不变。

## 约束符合性

- 未增加 `.vue` 自定义 `<style>` 或行内样式。
- 未修改 `src/components/ui/` 下的 Shadcn-Vue 生成源码。
- 未新增依赖，未使用 npm、yarn 或 bun。
- 新增颜色均通过 `primary`、`accent`、`secondary`、`card` 等语义变量引用。

## 验证

```powershell
pnpm --filter @password-detective/web lint
pnpm --filter @password-detective/web typecheck
pnpm --filter @password-detective/web test
pnpm --filter @password-detective/web build
pnpm --filter @password-detective/admin lint
pnpm --filter @password-detective/admin typecheck
pnpm --filter @password-detective/admin test
pnpm --filter @password-detective/admin build
```

桌面浏览器截图回归覆盖 `http://localhost:5173/login` 与 `http://localhost:5174/login`，确认字段纵向排列、双栏间距和窄屏回落规则正常。
