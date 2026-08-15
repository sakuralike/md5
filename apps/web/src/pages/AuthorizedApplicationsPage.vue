<script setup lang="ts">
import type { AuthorizedApplication } from "@password-detective/api-contract";
import { ref } from "vue";
import { Alert, AlertDescription, AlertTitle } from "../components/ui/alert";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../components/ui/card";
import { useAuthStore } from "../stores/auth";
import {
  listAuthorizedApplications,
  revokeAuthorizedApplication,
} from "../services/thirdPartyApps";

const auth = useAuthStore();
const applications = ref<AuthorizedApplication[]>([]);
const error = ref("");
const success = ref("");
const busy = ref("");

function formatDate(value: string | null): string {
  if (!value) return "尚未使用";
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(
    new Date(value),
  );
}

function messageFrom(caught: unknown, fallback: string): string {
  return caught instanceof Error ? caught.message : fallback;
}

async function load(): Promise<void> {
  try {
    const response = await listAuthorizedApplications(auth.accessToken);
    applications.value = response.items;
  } catch (caught) {
    error.value = messageFrom(caught, "无法加载已授权应用");
  }
}

async function revoke(application: AuthorizedApplication): Promise<void> {
  busy.value = application.app_id;
  error.value = "";
  success.value = "";
  try {
    await revokeAuthorizedApplication(auth.accessToken, application.app_id);
    applications.value = applications.value.filter((item) => item.app_id !== application.app_id);
    success.value = `已撤销“${application.app_name}”的授权`;
  } catch (caught) {
    error.value = messageFrom(caught, "撤销授权失败");
  } finally {
    busy.value = "";
  }
}

await load();
</script>

<template>
  <main class="mx-auto w-full max-w-5xl space-y-6 px-4 py-8">
    <header class="space-y-2">
      <h1 class="text-2xl font-semibold">已授权应用</h1>
      <p class="text-sm text-muted-foreground">管理通过 PKCE 接入密码侦探社的第三方桌面应用。</p>
    </header>
    <Alert v-if="error" variant="destructive">
      <AlertTitle>操作失败</AlertTitle>
      <AlertDescription>{{ error }}</AlertDescription>
    </Alert>
    <Alert v-if="success">
      <AlertTitle>操作成功</AlertTitle>
      <AlertDescription>{{ success }}</AlertDescription>
    </Alert>
    <Card v-for="application in applications" :key="application.app_id">
      <CardHeader>
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div>
            <CardTitle>{{ application.app_name }}</CardTitle>
            <CardDescription>{{ application.developer_name }} · {{ application.client_id }}</CardDescription>
          </div>
          <Button variant="destructive" :disabled="busy === application.app_id" @click="revoke(application)">
            {{ busy === application.app_id ? "处理中…" : "撤销授权" }}
          </Button>
        </div>
      </CardHeader>
      <CardContent class="space-y-3">
        <div class="flex flex-wrap gap-2">
          <Badge v-for="scope in application.scopes" :key="scope" variant="secondary">{{ scope }}</Badge>
        </div>
        <p class="text-sm text-muted-foreground">授权于：{{ formatDate(application.authorized_at) }}</p>
        <p class="text-sm text-muted-foreground">最近使用：{{ formatDate(application.last_used_at) }}</p>
      </CardContent>
    </Card>
    <Card v-if="applications.length === 0">
      <CardContent class="py-10 text-center text-sm text-muted-foreground">暂无已授权应用</CardContent>
    </Card>
  </main>
</template>
