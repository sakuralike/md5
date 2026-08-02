<script setup lang="ts">
import { useAdminAuthStore } from "./stores/auth";

const auth = useAdminAuthStore();
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <RouterLink class="brand" to="/">
        <span class="brand-mark" aria-hidden="true">🛡️</span>
        <span>密码侦探社 · 管理端</span>
      </RouterLink>
      <nav v-if="auth.isAuthenticated" class="nav" aria-label="管理导航">
        <RouterLink to="/">仪表盘</RouterLink>
        <RouterLink to="/candidates">候选审核</RouterLink>
        <RouterLink to="/trust-cases">举报申诉</RouterLink>
        <RouterLink to="/desktop-releases">桌面发布</RouterLink>
        <RouterLink to="/audit">审计日志</RouterLink>
        <button class="button secondary" @click="auth.logout()">退出</button>
      </nav>
    </header>
    <main class="main"><RouterView /></main>
  </div>
</template>
