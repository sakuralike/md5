<script setup lang="ts">
import { ref } from "vue";
import { RouterLink } from "vue-router";
import { Alert, AlertDescription } from "../components/ui/alert";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const loginName = ref("");
const password = ref("");
const totpCode = ref("");

async function submit(): Promise<void> {
  try {
    await auth.login(loginName.value, password.value, totpCode.value || undefined);
  } catch {
    // 统一错误已由会话状态展示。
  }
}
</script>

<template>
  <Card class="mx-auto w-full max-w-md border-white/60 bg-white/70 shadow-xl shadow-slate-200/40 backdrop-blur-xl">
    <CardHeader>
      <p class="text-xs font-semibold uppercase tracking-[0.24em] text-sky-600">安全会话</p>
      <CardTitle class="text-2xl">登录密码侦探社</CardTitle>
      <CardDescription>使用用户名或邮箱进入你的安全工作台。</CardDescription>
    </CardHeader>
    <CardContent>
      <form class="grid gap-5" @submit.prevent="submit">
        <Alert v-if="auth.error" variant="destructive" role="alert" aria-live="assertive">
          <AlertDescription>{{ auth.error }}</AlertDescription>
        </Alert>
        <div class="grid gap-2">
          <Label for="login">用户名或邮箱</Label>
          <Input id="login" v-model="loginName" autocomplete="username" required />
        </div>
        <div class="grid gap-2">
          <Label for="password">账号密码</Label>
          <Input id="password" v-model="password" type="password" autocomplete="current-password" required />
        </div>
        <div class="grid gap-2">
          <Label for="totp-code">TOTP 验证码（已启用时填写）</Label>
          <Input
            id="totp-code"
            v-model="totpCode"
            inputmode="numeric"
            autocomplete="one-time-code"
            pattern="[0-9]{6,8}"
            maxlength="8"
            placeholder="6～8 位数字"
          />
        </div>
        <Button type="submit" class="w-full" :disabled="auth.busy">
          {{ auth.busy ? "登录中…" : "登录" }}
        </Button>
        <div class="flex items-center justify-between text-sm text-muted-foreground">
          <RouterLink class="text-primary underline-offset-4 hover:underline" to="/forgot-password">
            忘记密码？
          </RouterLink>
          <span>还没有账号？<RouterLink class="text-primary underline-offset-4 hover:underline" to="/register">立即注册</RouterLink></span>
        </div>
      </form>
    </CardContent>
  </Card>
</template>
