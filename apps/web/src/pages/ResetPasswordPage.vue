<script setup lang="ts">
import { onMounted, ref } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { Alert, AlertDescription } from "../components/ui/alert";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { resetPassword } from "../services/auth";

const route = useRoute();
const router = useRouter();
const queryToken = route.query.token;
const token = ref(typeof queryToken === "string" ? queryToken : "");
const newPassword = ref("");
const confirmPassword = ref("");
const busy = ref(false);
const error = ref("");
const message = ref("");

onMounted(async () => {
  if (route.query.token) await router.replace({ path: "/reset-password" });
});

async function submit(): Promise<void> {
  error.value = "";
  message.value = "";
  if (!token.value) {
    error.value = "重置链接缺少有效凭证，请重新申请。";
    return;
  }
  if (newPassword.value !== confirmPassword.value) {
    error.value = "两次输入的新密码不一致。";
    return;
  }
  busy.value = true;
  try {
    const response = await resetPassword({ token: token.value, new_password: newPassword.value });
    message.value = response.message;
    newPassword.value = "";
    confirmPassword.value = "";
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "密码重置失败，请重新申请链接";
  } finally {
    busy.value = false;
  }
}

async function goToLogin(): Promise<void> {
  await router.push("/login");
}
</script>

<template>
  <Card class="mx-auto w-full max-w-md border-white/60 bg-white/70 shadow-xl shadow-slate-200/40 backdrop-blur-xl">
    <CardHeader>
      <p class="text-xs font-semibold uppercase tracking-[0.24em] text-sky-600">Credential reset</p>
      <CardTitle class="text-2xl">设置新密码</CardTitle>
      <CardDescription>重置凭证只在服务端短时有效。完成后所有旧密码重置凭证都会失效。</CardDescription>
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
          <Label for="reset-password">新密码</Label>
          <Input id="reset-password" v-model="newPassword" type="password" autocomplete="new-password" minlength="12" maxlength="128" required />
          <p class="text-xs text-muted-foreground">至少 12 位，并同时包含字母和数字。</p>
        </div>
        <div class="grid gap-2">
          <Label for="reset-password-confirm">确认新密码</Label>
          <Input id="reset-password-confirm" v-model="confirmPassword" type="password" autocomplete="new-password" minlength="12" maxlength="128" required />
        </div>
        <Button type="submit" class="w-full" :disabled="busy || Boolean(message)">
          {{ busy ? "保存中…" : "确认重置密码" }}
        </Button>
        <Button v-if="message" type="button" variant="outline" class="w-full" @click="goToLogin">
          返回登录
        </Button>
        <RouterLink v-else class="text-center text-sm text-primary underline-offset-4 hover:underline" to="/forgot-password">
          重新申请重置链接
        </RouterLink>
      </form>
    </CardContent>
  </Card>
</template>
