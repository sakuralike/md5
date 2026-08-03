<script setup lang="ts">
import { onMounted, ref } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { Alert, AlertDescription, AlertTitle } from "../components/ui/alert";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { verifyEmail } from "../services/auth";

const route = useRoute();
const router = useRouter();
const status = ref<"loading" | "success" | "error">("loading");
const message = ref("正在验证邮箱…");

onMounted(async () => {
  const queryToken = route.query.token;
  const token = typeof queryToken === "string" ? queryToken : "";
  await router.replace({ path: "/verify-email" });
  if (!token) {
    status.value = "error";
    message.value = "验证链接缺少有效凭证，请从邮件中的完整链接重新打开。";
    return;
  }
  try {
    const response = await verifyEmail({ token });
    status.value = "success";
    message.value = response.message;
  } catch (caught) {
    status.value = "error";
    message.value = caught instanceof Error ? caught.message : "邮箱验证失败，请稍后重试";
  }
});
</script>

<template>
  <Card class="mx-auto w-full max-w-md border-white/60 bg-white/70 shadow-xl shadow-slate-200/40 backdrop-blur-xl">
    <CardHeader>
      <p class="text-xs font-semibold uppercase tracking-[0.24em] text-sky-600">Email verification</p>
      <CardTitle class="text-2xl">邮箱验证</CardTitle>
      <CardDescription>验证结果只显示必要状态，不会在页面或日志中回显一次性凭证。</CardDescription>
    </CardHeader>
    <CardContent class="grid gap-5">
      <Alert v-if="status === 'error'" variant="destructive">
        <AlertTitle>验证未完成</AlertTitle>
        <AlertDescription>{{ message }}</AlertDescription>
      </Alert>
      <Alert v-else-if="status === 'success'">
        <AlertTitle>验证成功</AlertTitle>
        <AlertDescription>{{ message }}</AlertDescription>
      </Alert>
      <Alert v-else>
        <AlertDescription>{{ message }}</AlertDescription>
      </Alert>
      <Button v-if="status === 'success'" as-child class="w-full">
        <RouterLink to="/login">返回登录</RouterLink>
      </Button>
      <Button v-else as-child variant="outline" class="w-full">
        <RouterLink to="/login">返回登录</RouterLink>
      </Button>
    </CardContent>
  </Card>
</template>
