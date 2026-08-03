<script setup lang="ts">
import { ref } from "vue";
import { RouterLink } from "vue-router";
import { Alert, AlertDescription } from "../components/ui/alert";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { requestPasswordReset } from "../services/auth";

const email = ref("");
const busy = ref(false);
const error = ref("");
const message = ref("");

async function submit(): Promise<void> {
  busy.value = true;
  error.value = "";
  message.value = "";
  try {
    const response = await requestPasswordReset({ email: email.value });
    message.value = response.message;
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "请求发送失败，请稍后重试";
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <Card class="mx-auto w-full max-w-md border-white/60 bg-white/70 shadow-xl shadow-slate-200/40 backdrop-blur-xl">
    <CardHeader>
      <p class="text-xs font-semibold uppercase tracking-[0.24em] text-sky-600">Account recovery</p>
      <CardTitle class="text-2xl">找回账号密码</CardTitle>
      <CardDescription>输入注册邮箱。无论邮箱是否存在，页面都会使用统一提示，避免账号枚举。</CardDescription>
    </CardHeader>
    <CardContent>
      <form class="grid gap-5" @submit.prevent="submit">
        <Alert v-if="error" variant="destructive">
          <AlertDescription>{{ error }}</AlertDescription>
        </Alert>
        <Alert v-if="message">
          <AlertDescription>{{ message }}</AlertDescription>
        </Alert>
        <div class="grid gap-2">
          <Label for="recovery-email">注册邮箱</Label>
          <Input id="recovery-email" v-model="email" type="email" autocomplete="email" required />
        </div>
        <Button type="submit" class="w-full" :disabled="busy">
          {{ busy ? "发送中…" : "发送重置说明" }}
        </Button>
        <RouterLink class="text-center text-sm text-primary underline-offset-4 hover:underline" to="/login">
          返回登录
        </RouterLink>
      </form>
    </CardContent>
  </Card>
</template>
