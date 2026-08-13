<script setup lang="ts">
import { ref } from "vue";
import { RouterLink } from "vue-router";
import { Alert, AlertDescription } from "../components/ui/alert";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
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
  <section class="mx-auto grid min-h-[calc(100vh-11rem)] w-full max-w-5xl items-center gap-8 py-4 lg:grid-cols-[0.9fr_1.1fr] lg:py-8">
    <div class="space-y-5 px-2 text-center lg:text-left">
      <div class="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-gradient-to-br from-primary to-accent text-xl font-bold text-primary-foreground shadow-lg lg:mx-0">密</div>
      <div class="space-y-3">
        <p class="text-xs font-semibold uppercase tracking-[0.24em] text-primary">隐私优先的协作工作台</p>
        <h1 class="bg-gradient-to-r from-primary to-accent bg-clip-text text-4xl font-semibold tracking-tight text-transparent sm:text-5xl">从本地指纹开始，找到可信答案。</h1>
        <p class="mx-auto max-w-xl text-sm leading-7 text-muted-foreground lg:mx-0">压缩包始终留在本地。登录后可查看授权范围内的候选、贡献验证结果并参与安全社区。</p>
      </div>
      <div class="mx-auto flex max-w-xl flex-wrap justify-center gap-2 lg:mx-0 lg:justify-start">
        <span class="rounded-full border border-card/80 bg-card/70 px-3 py-1.5 text-xs text-muted-foreground shadow-sm backdrop-blur-xl">本地计算</span>
        <span class="rounded-full border border-card/80 bg-card/70 px-3 py-1.5 text-xs text-muted-foreground shadow-sm backdrop-blur-xl">最小披露</span>
        <span class="rounded-full border border-card/80 bg-card/70 px-3 py-1.5 text-xs text-muted-foreground shadow-sm backdrop-blur-xl">全程审计</span>
      </div>
    </div>

    <Card class="w-full border-card/80 bg-card/75 shadow-xl backdrop-blur-2xl">
      <CardHeader class="space-y-1.5 p-6 pb-5 sm:p-8 sm:pb-6">
        <p class="text-xs font-semibold uppercase tracking-[0.24em] text-primary">安全会话</p>
        <CardTitle class="text-2xl leading-tight sm:text-3xl">登录密码侦探社</CardTitle>
        <CardDescription class="text-sm leading-6">使用用户名或邮箱进入你的安全工作台。</CardDescription>
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
          <Button type="submit" class="h-11 w-full" :disabled="auth.busy">
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
