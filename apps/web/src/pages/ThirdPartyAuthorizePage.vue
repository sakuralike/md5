<script setup lang="ts">
import type {
  ThirdPartyAuthorizationDecisionRequest,
  ThirdPartyAuthorizationDetails,
  ThirdPartyAuthorizationRequest,
} from "@password-detective/api-contract";
import { ref } from "vue";
import { useRoute } from "vue-router";
import { Alert, AlertDescription, AlertTitle } from "../components/ui/alert";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "../components/ui/card";
import { useAuthStore } from "../stores/auth";
import {
  getThirdPartyAuthorizationRequest,
  submitThirdPartyAuthorization,
} from "../services/thirdPartyApps";

const route = useRoute();
const auth = useAuthStore();
const details = ref<ThirdPartyAuthorizationDetails | null>(null);
const error = ref("");
const busy = ref(false);

function queryValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

const request: ThirdPartyAuthorizationRequest = {
  response_type: queryValue(route.query.response_type) as "code",
  client_id: queryValue(route.query.client_id),
  redirect_uri: queryValue(route.query.redirect_uri),
  code_challenge: queryValue(route.query.code_challenge),
  state: queryValue(route.query.state),
  code_challenge_method: queryValue(route.query.code_challenge_method) as "S256",
  scope: queryValue(route.query.scope) || undefined,
};

function messageFrom(caught: unknown, fallback: string): string {
  return caught instanceof Error ? caught.message : fallback;
}

async function load(): Promise<void> {
  try {
    details.value = await getThirdPartyAuthorizationRequest(auth.accessToken, request);
  } catch (caught) {
    error.value = messageFrom(caught, "无法读取授权请求");
  }
}

async function decide(decision: "approve" | "deny"): Promise<void> {
  busy.value = true;
  error.value = "";
  try {
    const payload: ThirdPartyAuthorizationDecisionRequest = { ...request, decision };
    const result = await submitThirdPartyAuthorization(auth.accessToken, payload);
    if (typeof window !== "undefined") window.location.assign(result.redirect_url);
  } catch (caught) {
    error.value = messageFrom(caught, "授权处理失败，请稍后重试");
  } finally {
    busy.value = false;
  }
}

await load();
</script>

<template>
  <main class="mx-auto flex min-h-screen w-full max-w-3xl items-center px-4 py-10">
    <Card class="w-full">
      <CardHeader>
        <CardTitle>{{ details ? `${details.app_name}请求访问` : "第三方应用授权" }}</CardTitle>
        <CardDescription>
          请确认应用身份、回调地址和权限范围；授权后可以随时在账号安全设置中撤销。
        </CardDescription>
      </CardHeader>
      <CardContent class="space-y-6">
        <Alert v-if="error" variant="destructive">
          <AlertTitle>授权请求不可用</AlertTitle>
          <AlertDescription>{{ error }}</AlertDescription>
        </Alert>
        <template v-if="details">
          <section class="space-y-2">
            <h2 class="text-sm font-semibold">应用信息</h2>
            <p class="text-sm text-muted-foreground">开发者：{{ details.developer_name }}</p>
            <p class="text-sm text-muted-foreground">{{ details.description || "未提供应用描述" }}</p>
            <p class="break-all text-xs text-muted-foreground">回调地址：{{ details.redirect_uri }}</p>
          </section>
          <section class="space-y-3">
            <h2 class="text-sm font-semibold">请求的权限</h2>
            <div class="flex flex-wrap gap-2">
              <Badge v-for="scope in details.requested_scopes" :key="scope" variant="secondary">
                {{ scope }}
              </Badge>
            </div>
          </section>
          <p v-if="details.previously_authorized" class="text-sm text-muted-foreground">
            该应用曾经获得授权，本次确认会更新授权范围。
          </p>
        </template>
        <p v-else class="text-sm text-muted-foreground">正在加载授权请求…</p>
      </CardContent>
      <CardFooter class="flex flex-wrap justify-end gap-3">
        <Button variant="outline" :disabled="busy || !details" @click="decide('deny')">拒绝</Button>
        <Button :disabled="busy || !details" @click="decide('approve')">
          {{ busy ? "处理中…" : "同意授权" }}
        </Button>
      </CardFooter>
    </Card>
  </main>
</template>
