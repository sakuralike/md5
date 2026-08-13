# Web 账户入口与首页布局开发记录

## 目标

根据 `E:/只比主题/minimax/1.html` 的简白玻璃视觉参考，优化 Web 首页，并让登录后的主导航保持清晰：只显示首页、社区；账号相关能力进入头像菜单和独立用户中心。

## 实现

### 导航与头像菜单

- `apps/web/src/App.vue`：移除登录态下的多项功能导航，保留首页与社区。
- 未登录：右侧显示登录、注册。
- 已登录：右侧显示 Shadcn-Vue `Avatar`，点击触发 `DropdownMenu`；菜单展示用户名和邮箱，并提供用户中心、退出登录。
- 头像无图片字段时使用用户名首字母渐变回退，确保账号始终有可识别的头像入口。

### 独立用户中心

- 新增 `apps/web/src/pages/UserCenterPage.vue`。
- 路由为 `/user-center`，要求登录；历史 `/account/profile` 重定向到该页面。
- 页面集中展示身份、邮箱验证、TOTP、注册日期、信誉分、等级成长值和积分摘要。
- 快捷入口覆盖个人资料、账号安全、等级积分信誉、我的贡献、我的收藏、社区通知、活动记录和隐私中心。

### 首页布局

- `apps/web/src/pages/HomePage.vue` 改为居中标题和说明、胶囊查询方式切换、玻璃查询面板、集中精确查询结果和三项能力卡片。
- 继续使用现有 Shadcn-Vue Button/Input/Textarea/Checkbox 组件。
- 保留本地分块指纹计算、手工指纹查询、候选反馈、举报、揭示、贡献和授权声明逻辑。
- 未添加页面级 `<style>` 或硬编码颜色，新增视觉均使用 Tailwind 语义类。

## 验证

```text
pnpm --filter @password-detective/web typecheck
pnpm --filter @password-detective/web lint
pnpm --filter @password-detective/web test
pnpm --filter @password-detective/web build
```

以上四项均通过；Vitest 共 27 个测试文件、46 个测试通过。真实浏览器视觉回归仍需在部署环境执行。
