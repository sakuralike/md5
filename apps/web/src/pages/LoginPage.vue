<script setup lang="ts">
import { ref } from "vue";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const loginName = ref("");
const password = ref("");

async function submit() {
  try { await auth.login(loginName.value, password.value); } catch { /* store 已处理 */ }
}
</script>

<template>
  <form class="panel form stack" @submit.prevent="submit">
    <div><div class="eyebrow">安全会话</div><h1>登录</h1></div>
    <p v-if="auth.error" class="error" role="alert">{{ auth.error }}</p>
    <div class="field"><label for="login">用户名或邮箱</label><input id="login" v-model="loginName" autocomplete="username" required /></div>
    <div class="field"><label for="password">账号密码</label><input id="password" v-model="password" type="password" autocomplete="current-password" required /></div>
    <button class="button" :disabled="auth.busy">{{ auth.busy ? "登录中…" : "登录" }}</button>
    <p class="muted">还没有账号？<RouterLink to="/register">立即注册</RouterLink></p>
  </form>
</template>
