<script setup lang="ts">
import { ref } from "vue";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { useAdminAuthStore } from "../stores/auth";

const auth = useAdminAuthStore();
const loginName = ref("");
const password = ref("");
const totpCode = ref("");

async function submit(): Promise<void> {
  try {
    await auth.login(loginName.value, password.value, totpCode.value || undefined);
  } catch {
    // store 已处理。
  }
}
</script>

<template>
  <form class="panel form stack" @submit.prevent="submit">
    <div>
      <div class="eyebrow">独立管理入口</div>
      <h1>管理端登录</h1>
    </div>
    <p class="muted">审核员和系统管理员必须启用 TOTP；首次登录会引导完成绑定。</p>
    <p v-if="auth.error" class="error" role="alert">{{ auth.error }}</p>
    <div class="field">
      <Label for="login">用户名或邮箱</Label>
      <Input id="login" v-model="loginName" autocomplete="username" required />
    </div>
    <div class="field">
      <Label for="password">密码</Label>
      <Input
        id="password"
        v-model="password"
        type="password"
        autocomplete="current-password"
        required
      />
    </div>
    <div class="field">
      <Label for="totp">动态验证码（已启用时必填）</Label>
      <Input
        id="totp"
        v-model="totpCode"
        inputmode="numeric"
        autocomplete="one-time-code"
        minlength="6"
        maxlength="8"
      />
    </div>
    <Button type="submit" :disabled="auth.busy">
      {{ auth.busy ? "验证中…" : "登录管理端" }}
    </Button>
  </form>
</template>
