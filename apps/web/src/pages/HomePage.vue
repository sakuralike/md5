<script setup lang="ts">
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
</script>

<template>
  <section class="hero">
    <div class="panel">
      <div class="eyebrow">本地计算 · 精确匹配 · 社区验证</div>
      <h1>文件留在本地，证据连接答案。</h1>
      <p class="lead">
        密码侦探社使用整个压缩包的 SHA-256/MD5 指纹进行精确查询，不上传文件内容，
        并通过独立的本地解压验证证据维护候选密码可信度。
      </p>
      <div class="actions">
        <RouterLink v-if="!auth.isAuthenticated" class="button" to="/register">创建账号</RouterLink>
        <RouterLink v-else class="button" to="/security">查看账号安全</RouterLink>
        <span class="badge">M1 工程基础</span>
      </div>
    </div>
    <aside class="panel stack">
      <h2>隐私边界</h2>
      <p>浏览器只计算文件指纹；压缩包内容不会发送到服务端。</p>
      <p>匿名用户只能查看匹配状态，完整密码揭示需要登录、配额和审计。</p>
      <p>查询功能将在 M2 阶段开放。</p>
    </aside>
  </section>
  <section class="grid" aria-label="开发模块状态">
    <article class="card"><span class="badge">已接入</span><h2>账号认证</h2><p class="muted">注册、登录、刷新轮换、退出和会话撤销。</p></article>
    <article class="card"><span class="badge">M2</span><h2>指纹查询</h2><p class="muted">浏览器分块计算 SHA-256/MD5 并精确匹配。</p></article>
    <article class="card"><span class="badge">M3</span><h2>桌面验证</h2><p class="muted">在 Windows 本地测试 ZIP/7z 并提交签名回执。</p></article>
  </section>
</template>
