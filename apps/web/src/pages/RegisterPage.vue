<script setup lang="ts">
import type { RegistrationMode } from "@password-detective/api-contract";
import { KeyRound, LoaderCircle, UserPlus } from "lucide-vue-next";
import { onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getPublicSiteConfig } from "../services/site";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const route = useRoute();
const username = ref("");
const email = ref("");
const password = ref("");
const inviteCode = ref("");
const referralCode = ref(
  typeof route.query.ref === "string" ? route.query.ref.trim().toLowerCase() : "",
);
const registrationMode = ref<RegistrationMode>("open");
const policyLoading = ref(true);

onMounted(async () => {
  try {
    registrationMode.value = (await getPublicSiteConfig()).registration.mode;
  } finally {
    policyLoading.value = false;
  }
});

async function submit(): Promise<void> {
  try {
    await auth.register(
      username.value,
      email.value,
      password.value,
      registrationMode.value === "invite_only" ? inviteCode.value : undefined,
      referralCode.value || undefined,
    );
  } catch {
    // Store 统一展示服务端返回的注册错误。
  }
}
</script>

<template>
  <form class="mx-auto w-full max-w-lg space-y-6 rounded-lg border bg-card p-6 text-card-foreground shadow-sm" @submit.prevent="submit">
    <header class="space-y-2">
      <div class="flex items-center gap-2 text-sm font-medium text-primary">
        <UserPlus class="h-4 w-4" />加入侦探社
      </div>
      <h1 class="text-2xl font-semibold">创建账号</h1>
    </header>
    <p v-if="auth.error" class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{{ auth.error }}</p>
    <div class="space-y-2">
      <Label for="username">用户名</Label>
      <Input id="username" v-model="username" minlength="3" maxlength="32" pattern="[A-Za-z0-9_]+" autocomplete="username" required />
    </div>
    <div class="space-y-2">
      <Label for="email">邮箱</Label>
      <Input id="email" v-model="email" type="email" autocomplete="email" required />
    </div>
    <div class="space-y-2">
      <Label for="new-password">密码</Label>
      <Input id="new-password" v-model="password" type="password" minlength="12" maxlength="128" autocomplete="new-password" required />
      <p class="text-xs text-muted-foreground">至少 12 位，并包含字母和数字。</p>
    </div>
    <div v-if="registrationMode === 'invite_only'" class="space-y-2">
      <Label for="invite-code">邀请码</Label>
      <div class="relative">
        <KeyRound class="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input id="invite-code" v-model="inviteCode" class="pl-9" maxlength="128" autocomplete="off" required />
      </div>
    </div>
    <div v-if="referralCode" class="space-y-2 rounded-md border border-primary/30 bg-primary/5 p-3">
      <Label for="referral-code">邀请链接</Label>
      <Input id="referral-code" :model-value="referralCode" readonly />
      <p class="text-xs text-muted-foreground">已识别邀请链接，注册成功后你和邀请人各获得积分奖励。</p>
    </div>
    <Button class="w-full" :disabled="auth.busy || policyLoading">
      <LoaderCircle v-if="auth.busy || policyLoading" class="mr-2 h-4 w-4 animate-spin" />
      {{ policyLoading ? "读取注册策略" : auth.busy ? "创建中…" : "注册并登录" }}
    </Button>
  </form>
</template>
