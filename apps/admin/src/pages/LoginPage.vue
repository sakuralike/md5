<script setup lang="ts">
import { ref } from "vue";
import { Button } from "../components/ui/button";
import { Checkbox } from "../components/ui/checkbox";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { useAdminAuthStore } from "../stores/auth";

const auth = useAdminAuthStore();
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
    // store 已处理。
  }
}
</script>

<template>
  <section class="mx-auto grid min-h-[calc(100vh-9rem)] w-full max-w-5xl grid-cols-1 items-center gap-8 py-6 lg:grid-cols-[0.95fr_1.05fr] lg:gap-10">
    <div class="space-y-6 px-2 text-center lg:text-left">
      <div class="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-gradient-to-br from-primary to-accent text-xl text-primary-foreground shadow-lg lg:mx-0">🛡️</div>
      <div class="space-y-3">
        <p class="text-xs font-semibold uppercase tracking-[0.24em] text-primary">独立管理入口</p>
        <h2 class="bg-gradient-to-r from-primary to-accent bg-clip-text text-4xl font-semibold tracking-tight text-transparent sm:text-5xl">安全运营从受控身份开始。</h2>
      </div>
      <p class="mx-auto max-w-xl text-sm leading-7 text-muted-foreground lg:mx-0">
        管理员登录、可选 TOTP、多角色治理与关键写操作审计均在独立入口完成。TOTP 默认关闭，可按需主动启用；启用后登录必须填写动态验证码。页面不会展示候选密码、刷新令牌或真实个人信息。
      </p>
      <ul class="mx-auto flex max-w-xl flex-wrap justify-center gap-2 text-xs text-muted-foreground lg:mx-0 lg:justify-start">
        <li class="rounded-full border border-card/80 bg-card/70 px-3 py-1.5 shadow-sm backdrop-blur-xl">TOTP 默认关闭</li>
        <li class="rounded-full border border-card/80 bg-card/70 px-3 py-1.5 shadow-sm backdrop-blur-xl">不可变审计</li>
        <li class="rounded-full border border-card/80 bg-card/70 px-3 py-1.5 shadow-sm backdrop-blur-xl">最小披露</li>
      </ul>
    </div>

    <form
      data-testid="admin-login-form"
      class="mx-auto flex w-full max-w-lg flex-col gap-5 rounded-3xl border border-card/80 bg-card/75 p-6 text-card-foreground shadow-xl backdrop-blur-2xl sm:p-8"
      aria-labelledby="admin-login-title"
      @submit.prevent="submit"
    >
      <header class="space-y-2">
        <p class="text-xs font-semibold uppercase tracking-[0.22em] text-primary">安全会话</p>
        <h1 id="admin-login-title" class="text-2xl font-semibold tracking-tight sm:text-3xl">管理端登录</h1>
        <p class="text-sm leading-6 text-muted-foreground">使用用户名或邮箱与密码登录；TOTP 默认关闭，仅已主动启用的账号需要填写动态验证码。</p>
      </header>

      <div v-if="auth.error" class="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive" role="alert" aria-live="assertive">
        {{ auth.error }}
      </div>

      <div class="flex flex-col gap-2">
        <Label for="login">用户名或邮箱</Label>
        <Input id="login" v-model="loginName" class="h-11" autocomplete="username" required />
      </div>
      <div class="flex flex-col gap-2">
        <Label for="password">密码</Label>
        <Input id="password" v-model="password" class="h-11" type="password" autocomplete="current-password" required />
      </div>
      <div class="flex flex-col gap-2">
        <Label for="totp">动态验证码（仅已启用 TOTP 时填写）</Label>
        <Input id="totp" v-model="totpCode" class="h-11" inputmode="numeric" autocomplete="one-time-code" minlength="6" maxlength="8" />
      </div>
      <div class="flex items-start gap-3 rounded-xl border border-border/70 bg-muted/40 px-3 py-3">
        <Checkbox id="admin-remember-login" v-model="rememberLogin" class="mt-0.5" />
        <div class="grid gap-1">
          <Label for="admin-remember-login" class="cursor-pointer font-medium">记住登录账号</Label>
          <p class="text-xs leading-5 text-muted-foreground">仅保存用户名或邮箱；密码由浏览器密码管理器处理，管理端不保存明文密码。</p>
        </div>
      </div>
      <Button class="h-11 w-full" type="submit" :disabled="auth.busy">
        {{ auth.busy ? "验证中…" : "登录管理端" }}
      </Button>
      <p class="text-center text-xs leading-5 text-muted-foreground">仅使用分配给你的管理员账号；不要共享密码，已启用 TOTP 时也不要共享动态验证码。</p>
    </form>
  </section>
</template>
