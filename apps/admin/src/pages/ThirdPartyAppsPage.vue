<script setup lang="ts">
import type { ThirdPartyApp, ThirdPartyAppCreateRequest } from "@password-detective/api-contract";
import { ref } from "vue";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Checkbox } from "../components/ui/checkbox";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { useAdminAuthStore } from "../stores/auth";
import {
  approveThirdPartyApp,
  createThirdPartyApp,
  listThirdPartyApps,
  restoreThirdPartyApp,
  revokeThirdPartyApp,
  suspendThirdPartyApp,
} from "../services/thirdPartyApps";

const auth = useAdminAuthStore();
const applications = ref<ThirdPartyApp[]>([]);
const name = ref("");
const developerName = ref("");
const description = ref("");
const redirectUrisText = ref("");
const scopesText = ref("profile:read\ndesktop:verification");
const reviewNote = ref("");
const trustedVerification = ref(false);
const error = ref("");
const success = ref("");
const busy = ref("");

function messageFrom(caught: unknown, fallback: string): string {
  return caught instanceof Error ? caught.message : fallback;
}

function lines(value: string): string[] {
  return [...new Set(value.split(/\r?\n|,/).map((item) => item.trim()).filter(Boolean))];
}

function statusLabel(status: ThirdPartyApp["status"]): string {
  return {
    draft: "草稿",
    pending_review: "待审核",
    approved: "已审核",
    suspended: "已暂停",
    revoked: "已撤销",
  }[status];
}

function statusVariant(status: ThirdPartyApp["status"]): "default" | "secondary" | "destructive" | "outline" {
  if (status === "approved") return "default";
  if (status === "suspended" || status === "revoked") return "destructive";
  if (status === "pending_review") return "secondary";
  return "outline";
}

async function load(): Promise<void> {
  try {
    applications.value = (await listThirdPartyApps(auth.accessToken)).items;
  } catch (caught) {
    error.value = messageFrom(caught, "无法加载第三方应用");
  }
}

function clearFeedback(): void {
  error.value = "";
  success.value = "";
}

async function create(): Promise<void> {
  clearFeedback();
  busy.value = "create";
  try {
    const payload: ThirdPartyAppCreateRequest = {
      name: name.value.trim(),
      developer_name: developerName.value.trim(),
      description: description.value.trim(),
      redirect_uris: lines(redirectUrisText.value),
      scopes: lines(scopesText.value),
    };
    const created = await createThirdPartyApp(auth.accessToken, payload);
    applications.value = [created, ...applications.value];
    success.value = `应用“${created.name}”已创建；请妥善保存本次返回的管理密钥。`;
    name.value = "";
    developerName.value = "";
    description.value = "";
    redirectUrisText.value = "";
  } catch (caught) {
    error.value = messageFrom(caught, "创建应用失败");
  } finally {
    busy.value = "";
  }
}

async function approve(application: ThirdPartyApp): Promise<void> {
  clearFeedback();
  busy.value = application.id;
  try {
    const updated = await approveThirdPartyApp(auth.accessToken, application.id, {
      review_note: reviewNote.value.trim() || null,
      trusted_verification_enabled: trustedVerification.value,
    });
    applications.value = applications.value.map((item) => item.id === updated.id ? updated : item);
    success.value = `应用“${updated.name}”已审核通过`;
  } catch (caught) {
    error.value = messageFrom(caught, "审核应用失败");
  } finally {
    busy.value = "";
  }
}

async function mutate(application: ThirdPartyApp, action: "suspend" | "restore" | "revoke"): Promise<void> {
  clearFeedback();
  busy.value = `${action}:${application.id}`;
  try {
    const mutations = { suspend: suspendThirdPartyApp, restore: restoreThirdPartyApp, revoke: revokeThirdPartyApp };
    const updated = await mutations[action](auth.accessToken, application.id);
    applications.value = applications.value.map((item) => item.id === updated.id ? updated : item);
    success.value = `应用“${updated.name}”状态已更新为${statusLabel(updated.status)}`;
  } catch (caught) {
    error.value = messageFrom(caught, "更新应用状态失败");
  } finally {
    busy.value = "";
  }
}

await load();
</script>
<template>
  <main class="mx-auto w-full max-w-7xl space-y-6 px-4 py-8">
    <header class="space-y-2">
      <h1 class="text-2xl font-semibold">第三方应用治理</h1>
      <p class="text-sm text-muted-foreground">管理员手动创建、审核和暂停第三方桌面端应用；后续可扩展开发者自助申请。</p>
    </header>
    <div v-if="error" class="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">{{ error }}</div>
    <div v-if="success" class="rounded-md border border-primary/30 bg-primary/5 p-4 text-sm text-primary">{{ success }}</div>
    <div class="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(20rem,24rem)]">
      <section class="rounded-lg border bg-card p-6 shadow-sm">
        <div class="mb-5 space-y-1"><h2 class="text-lg font-semibold">已登记应用</h2><p class="text-sm text-muted-foreground">查看 Client ID、Scope、审核状态与可信验证权限。</p></div>
        <div class="space-y-4">
          <article v-for="application in applications" :key="application.id" class="space-y-4 rounded-md border p-4">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div><h3 class="font-semibold">{{ application.name }}</h3><p class="text-sm text-muted-foreground">{{ application.developer_name }} · {{ application.client_id }}</p></div>
              <Badge :variant="statusVariant(application.status)">{{ statusLabel(application.status) }}</Badge>
            </div>
            <p class="text-sm text-muted-foreground">{{ application.description || "未提供应用描述" }}</p>
            <div class="flex flex-wrap gap-2"><Badge v-for="scope in application.approved_scopes.length ? application.approved_scopes : application.requested_scopes" :key="scope" variant="secondary">{{ scope }}</Badge></div>
            <p class="break-all text-xs text-muted-foreground">回调地址：{{ application.redirect_uris.join("、") }}</p>
            <div class="flex flex-wrap gap-2">
              <Button v-if="application.status === 'draft' || application.status === 'pending_review'" size="sm" :disabled="busy === application.id" @click="approve(application)">审核通过</Button>
              <Button v-if="application.status !== 'revoked'" size="sm" variant="outline" :disabled="application.status !== 'approved' || busy === `suspend:${application.id}`" @click="mutate(application, 'suspend')">暂停应用</Button>
              <Button v-if="application.status === 'suspended'" size="sm" variant="outline" :disabled="busy === `restore:${application.id}`" @click="mutate(application, 'restore')">恢复应用</Button>
              <Button v-if="application.status !== 'revoked'" size="sm" variant="destructive" :disabled="busy === `revoke:${application.id}`" @click="mutate(application, 'revoke')">撤销应用</Button>
            </div>
          </article>
          <p v-if="applications.length === 0" class="py-10 text-center text-sm text-muted-foreground">暂无第三方应用</p>
        </div>
      </section>
      <section class="rounded-lg border bg-card p-6 shadow-sm">
        <div class="mb-5 space-y-1"><h2 class="text-lg font-semibold">创建应用</h2><p class="text-sm text-muted-foreground">管理员手动登记；管理密钥只在创建或轮换时显示。</p></div>
        <form class="space-y-4" @submit.prevent="create">
          <div class="space-y-2"><Label for="third-party-name">应用名称</Label><Input id="third-party-name" v-model="name" required /></div>
          <div class="space-y-2"><Label for="third-party-developer">开发者名称</Label><Input id="third-party-developer" v-model="developerName" required /></div>
          <div class="space-y-2"><Label for="third-party-description">应用描述</Label><Textarea id="third-party-description" v-model="description" /></div>
          <div class="space-y-2"><Label for="third-party-redirects">回调地址（每行一个）</Label><Textarea id="third-party-redirects" v-model="redirectUrisText" required /></div>
          <div class="space-y-2"><Label for="third-party-scopes">申请 Scope（每行一个）</Label><Textarea id="third-party-scopes" v-model="scopesText" required /></div>
          <div class="flex items-center gap-2"><Checkbox id="trusted-verification" v-model="trustedVerification" /><Label for="trusted-verification">可信验证直入总哈希池</Label></div>
          <div class="space-y-2"><Label for="third-party-review-note">审核备注</Label><Textarea id="third-party-review-note" v-model="reviewNote" /></div>
          <Button type="submit" :disabled="busy === 'create'">{{ busy === 'create' ? "创建中…" : "创建应用" }}</Button>
        </form>
      </section>
    </div>
  </main>
</template>
