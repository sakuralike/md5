<script setup lang="ts">
import { useAuthStore } from "./stores/auth";

const auth = useAuthStore();
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <RouterLink class="brand" to="/">
        <span class="brand-mark" aria-hidden="true">🔎</span>
        <span>密码侦探社</span>
      </RouterLink>
      <nav class="nav" aria-label="主导航">
        <RouterLink to="/">首页</RouterLink>
        <RouterLink v-if="auth.isAuthenticated" to="/security">账号安全</RouterLink>
        <RouterLink v-if="!auth.isAuthenticated" to="/login">登录</RouterLink>
        <RouterLink v-if="!auth.isAuthenticated" to="/register">注册</RouterLink>
        <button v-if="auth.isAuthenticated" class="button secondary" @click="auth.logout()">
          退出
        </button>
      </nav>
    </header>
    <main class="main">
      <RouterView />
    </main>
  </div>
</template>
