<script setup lang="ts">
import { ref } from "vue";
import { RouterLink } from "vue-router";
import { Alert, AlertDescription } from "../components/ui/alert";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader } from "../components/ui/card";
import { Checkbox } from "../components/ui/checkbox";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const rememberedLogin = auth.getRememberedLogin();
const loginName = ref(rememberedLogin);
const password = ref("");
const totpCode = ref("");
const rememberLogin = ref(Boolean(rememberedLogin));

async function submit(): Promise<void> {
  try {
    await auth.login(
      loginName.value,
      password.value,
      totpCode.value || undefined,
      rememberLogin.value,
    );
  } catch {
    // 统一错误已由会话状态展示。
  }
}
</script>

<template>
  <section class="mx-auto flex min-h-[calc(100vh-11rem)] w-full max-w-md items-center px-4 py-10">
    <Card class="glass-modal w-full rounded-[1.5rem]">
      <CardHeader class="space-y-1.5 p-6 pb-5 sm:p-8 sm:pb-6">
        <p class="text-xs font-semibold uppercase tracking-[0.24em] text-primary">安全会话</p>
        <h1 class="text-2xl font-semibold leading-tight sm:text-3xl">登录密码侦探社</h1>
        <CardDescription class="text-sm leading-6">欢迎回来，使用用户名或邮箱进入你的安全工作台。</CardDescription>
      </CardHeader>
      <CardContent class="px-6 pb-6 pt-0 sm:px-8 sm:pb-8">
        <form data-testid="user-login-form" class="flex flex-col gap-5" @submit.prevent="submit">
          <Alert v-if="auth.error" variant="destructive" role="alert" aria-live="assertive">
            <AlertDescription>{{ auth.error }}</AlertDescription>
          </Alert>
          <div class="flex flex-col gap-2">
            <Label for="login">用户名或邮箱</Label>
            <Input id="login" v-model="loginName" class="h-11" autocomplete="username" required />
          </div>
          <div class="flex flex-col gap-2">
            <Label for="password">账号密码</Label>
            <Input id="password" v-model="password" class="h-11" type="password" autocomplete="current-password" required />
          </div>
          <div class="flex flex-col gap-2">
            <Label for="totp-code">TOTP 验证码（已启用时填写）</Label>
            <Input
              id="totp-code"
              v-model="totpCode"
              class="h-11"
              inputmode="numeric"
              autocomplete="one-time-code"
              pattern="[0-9]{6,8}"
              maxlength="8"
              placeholder="6～8 位数字"
            />
          </div>
          <div class="flex items-start gap-3 rounded-xl border border-border/70 bg-muted/40 px-3 py-3">
            <Checkbox id="remember-login" v-model="rememberLogin" class="mt-0.5" />
            <div class="grid gap-1">
              <Label for="remember-login" class="cursor-pointer font-medium">记住登录账号</Label>
              <p class="text-xs leading-5 text-muted-foreground">仅保存用户名或邮箱；密码由浏览器密码管理器处理，本站不会保存明文密码。</p>
            </div>
          </div>
          <Button type="submit" class="btn-gradient h-11 w-full" :disabled="auth.busy">
            {{ auth.busy ? "登录中…" : "登录" }}
          </Button>
          <div class="flex flex-col gap-2 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
            <RouterLink class="text-primary underline decoration-1 underline-offset-4 hover:decoration-2" to="/forgot-password">
              忘记密码？
            </RouterLink>
            <span>
              还没有账号？
              <RouterLink class="text-primary underline decoration-1 underline-offset-4 hover:decoration-2" to="/register">立即注册</RouterLink>
            </span>
          </div>
        </form>
      </CardContent>
    </Card>
  </section>
</template>
