<script setup lang="ts">
import { ref } from "vue";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const username = ref("");
const email = ref("");
const password = ref("");

async function submit() {
  try { await auth.register(username.value, email.value, password.value); } catch { /* store 已处理 */ }
}
</script>

<template>
  <form class="panel form stack" @submit.prevent="submit">
    <div><div class="eyebrow">加入侦探社</div><h1>创建账号</h1></div>
    <p v-if="auth.error" class="error" role="alert">{{ auth.error }}</p>
    <div class="field"><Label for="username">用户名</Label><Input id="username" v-model="username" minlength="3" maxlength="32" pattern="[A-Za-z0-9_]+" autocomplete="username" required /></div>
    <div class="field"><Label for="email">邮箱</Label><Input id="email" v-model="email" type="email" autocomplete="email" required /></div>
    <div class="field"><Label for="new-password">密码</Label><Input id="new-password" v-model="password" type="password" minlength="12" maxlength="128" autocomplete="new-password" required /><small class="muted">至少 12 位，并包含字母和数字。</small></div>
    <Button class="button" :disabled="auth.busy">{{ auth.busy ? "创建中…" : "注册并登录" }}</Button>
  </form>
</template>
