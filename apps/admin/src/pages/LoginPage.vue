<script setup lang="ts">
import { ref } from "vue";
import { useAdminAuthStore } from "../stores/auth";

const auth = useAdminAuthStore();
const loginName = ref("");
const password = ref("");
async function submit() { try { await auth.login(loginName.value, password.value); } catch { /* store 已处理 */ } }
</script>

<template>
  <form class="panel form stack" @submit.prevent="submit">
    <div><div class="eyebrow">独立管理入口</div><h1>管理端登录</h1></div>
    <p class="muted">仅审核员和系统管理员可访问；M4 将启用强制 TOTP 二次验证。</p>
    <p v-if="auth.error" class="error" role="alert">{{ auth.error }}</p>
    <div class="field"><label for="login">用户名或邮箱</label><input id="login" v-model="loginName" autocomplete="username" required /></div>
    <div class="field"><label for="password">密码</label><input id="password" v-model="password" type="password" autocomplete="current-password" required /></div>
    <button class="button" :disabled="auth.busy">{{ auth.busy ? "验证中…" : "登录管理端" }}</button>
  </form>
</template>
