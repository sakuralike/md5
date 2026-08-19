# AGENTS.md

## 项目文档规则
- 项目文档的唯一维护格式是 Markdown（`.md`）。
- 当前有效文档位于 `项目文档/`；历史材料位于 `项目文档/历史文档/`。
- 不新增或直接编辑 DOCX/PDF。若用户临时要求导出，必须从 Markdown 生成，且 Markdown 仍是唯一事实来源。
- 修改需求、架构、API、数据模型、开发计划或验收标准时，同步更新 `项目文档/文档变更记录.md`。
- 原始历史文档与当前规格冲突时，以 `项目文档/密码侦探社项目规格说明书-v3.0.md` 为准。
- 文档使用 UTF-8、相对链接、带语言标识的代码围栏；流程和架构图优先使用 Mermaid。
- 文档示例只能使用合成数据，不记录真实密码、令牌、密钥或个人信息。

# AGENTS.md - 前端开发规范

## 包管理器规范
- **强制使用 pnpm**：本项目唯一指定的包管理器是 pnpm。
- **禁止命令**：严禁使用 `npm install`、`yarn` 或 `bun`。
- **依赖管理**：所有依赖安装、更新、卸载必须通过 pnpm 执行（如 `pnpm add <pkg>`）。
- **锁定文件**：必须维护 `pnpm-lock.yaml`，若检测到 `package-lock.json` 或 `yarn.lock` 请提示删除。

## 项目技术栈
- 框架：Vue 3 (Composition API)
- UI 库：Shadcn-Vue
- 样式方案：Tailwind CSS 3.x
- 语言：TypeScript (严格模式)

## 核心开发规范
### UI 与组件
- 所有 UI 组件必须优先使用 Shadcn-Vue。需要新组件时，先运行 `npx shadcn-vue@latest add [组件名]`。
- 绝对不要引入 Element Plus、Ant Design Vue 等其他传统 UI 库。
- 禁止使用原生 HTML 标签（如 `<button>`、`<input>`）来替代 Shadcn-Vue 的基础组件。

### 样式编写
- 必须使用 Tailwind CSS 的工具类（Utility Classes）进行样式编写。
- 禁止在 `.vue` 文件中编写自定义的 `<style>` 块或行内样式（Inline Styles）。
- 颜色必须使用 Tailwind 配置中的语义化变量（如 `bg-primary`、`text-muted-foreground`），禁止硬编码十六进制颜色值（如 `#333`）。
- 响应式设计必须遵循 Mobile-first（移动端优先）原则。

### 代码与工程
- 使用 Vue 3 的 `<script setup lang="ts">` 语法。
- 所有组件必须使用 PascalCase 命名。
- 禁止使用 `any` 类型，必须定义明确的 TypeScript Interface。
- 不要修改 `src/components/ui/` 目录下由 CLI 自动生成的组件源码，除非有明确的定制需求。

## 关键命令
- 安装组件：`npx shadcn-vue@latest add [组件名]`
- 开发环境：`pnpm dev`
- 代码检查：`pnpm lint`
- 类型检查：`pnpm typecheck`

## 交付标准 (What "Done" Means)
- 代码无 TypeScript 类型错误。
- 通过 ESLint 检查。
- 没有任何自定义 CSS 样式，完全依赖 Tailwind 类。
- 新增的复杂组件必须包含基础的渲染测试。