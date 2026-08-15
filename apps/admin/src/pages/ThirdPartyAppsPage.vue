<script setup lang="ts">
import { THIRD_PARTY_REQUESTABLE_SCOPE_OPTIONS, type ThirdPartyApp, type ThirdPartyAppCreateRequest } from "@password-detective/api-contract";
import { onMounted, onServerPrefetch, ref } from "vue";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "../components/ui/card";
import { Checkbox } from "../components/ui/checkbox";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { useAdminAuthStore } from "../stores/auth";
import {
  approveThirdPartyApp,
  approveThirdPartyApplicationRequest,
  createThirdPartyApp,
  listThirdPartyApps,
  listThirdPartyApplicationRequests,
  rejectThirdPartyApplicationRequest,
  restoreThirdPartyApp,
  revokeThirdPartyApp,
  suspendThirdPartyApp,
  type ThirdPartyApplicationRequest,
} from "../services/thirdPartyApps";

const auth = useAdminAuthStore();
const applications = ref<ThirdPartyApp[]>([]);
const selfServiceRequests = ref<ThirdPartyApplicationRequest[]>([]);
const name = ref("");
const developerName = ref("");
const description = ref("");
const redirectUrisText = ref("");
const selectedScopes = ref<string[]>(["profile:read", "desktop:verification"]);
const selectableScopes = THIRD_PARTY_REQUESTABLE_SCOPE_OPTIONS;
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

function updateScopeSelection(scope: string, checked: boolean | "indeterminate"): void {
  selectedScopes.value = checked === true
    ? [...new Set([...selectedScopes.value, scope])]
    : selectedScopes.value.filter((selectedScope) => selectedScope !== scope);
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
    const [applicationsResponse, requestsResponse] = await Promise.all([
      listThirdPartyApps(auth.accessToken),
      listThirdPartyApplicationRequests(auth.accessToken),
    ]);
    applications.value = applicationsResponse.items;
    selfServiceRequests.value = requestsResponse.items;
  } catch (caught) {
    error.value = messageFrom(caught, "无法加载第三方应用治理数据");
  }
}

function clearFeedback(): void {
  error.value = "";
  success.value = "";
}

async function create(): Promise<void> {
  clearFeedback();
  if (selectedScopes.value.length === 0) {
    error.value = "请至少选择一个申请 Scope。";
    return;
  }
  busy.value = "create";
  try {
    const payload: ThirdPartyAppCreateRequest = {
      name: name.value.trim(),
      developer_name: developerName.value.trim(),
      description: description.value.trim(),
      redirect_uris: lines(redirectUrisText.value),
      scopes: selectedScopes.value,
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

function requestStatusLabel(status: ThirdPartyApplicationRequest["status"]): string {
  return { draft: "草稿", pending_review: "待审核", rejected: "已驳回", approved: "已通过" }[status];
}

async function approveSelfServiceRequest(request: ThirdPartyApplicationRequest): Promise<void> {
  clearFeedback();
  busy.value = `request-approve:${request.id}`;
  try {
    await approveThirdPartyApplicationRequest(auth.accessToken, request.id, {
      review_note: reviewNote.value.trim() || null,
      approved_scopes: request.requested_scopes,
      trusted_verification_enabled: trustedVerification.value,
    });
    await load();
    success.value = `已审核通过“${request.name}”；可用第三方应用已创建。`;
  } catch (caught) {
    error.value = messageFrom(caught, "审核开发者申请失败");
  } finally {
    busy.value = "";
  }
}

async function rejectSelfServiceRequest(request: ThirdPartyApplicationRequest): Promise<void> {
  const note = reviewNote.value.trim();
  if (!note) {
    error.value = "驳回开发者申请前必须填写审核备注。";
    return;
  }
  clearFeedback();
  busy.value = `request-reject:${request.id}`;
  try {
    await rejectThirdPartyApplicationRequest(auth.accessToken, request.id, note);
    await load();
    success.value = `已驳回“${request.name}”，开发者可直接修改原申请并重新提交。`;
  } catch (caught) {
    error.value = messageFrom(caught, "驳回开发者申请失败");
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

onServerPrefetch(load);
onMounted(() => {
  void load();
});
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
          <fieldset class="space-y-3"><legend class="text-sm font-medium leading-none">申请 Scope</legend><p class="text-xs text-muted-foreground">请选择该应用实际需要的权限。可信验证直入总哈希池仍需在创建后单独审核授予。</p><div class="grid gap-3 sm:grid-cols-2"><div v-for="option in selectableScopes" :key="option.value" class="flex gap-3 rounded-lg border p-3"><Checkbox :id="`third-party-scope-${option.value}`" :checked="selectedScopes.includes(option.value)" @update:checked="updateScopeSelection(option.value, $event)" /><Label :for="`third-party-scope-${option.value}`" class="grid cursor-pointer gap-1 leading-snug"><span class="font-medium text-foreground">{{ option.label }}</span><code class="text-xs text-muted-foreground">{{ option.value }}</code><span class="text-xs font-normal text-muted-foreground">{{ option.description }}</span></Label></div></div></fieldset>
          <div class="flex items-center gap-2"><Checkbox id="trusted-verification" v-model="trustedVerification" /><Label for="trusted-verification">可信验证直入总哈希池</Label></div>
          <div class="space-y-2"><Label for="third-party-review-note">审核备注</Label><Textarea id="third-party-review-note" v-model="reviewNote" /></div>
          <Button type="submit" :disabled="busy === 'create'">{{ busy === 'create' ? "创建中…" : "创建应用" }}</Button>
        </form>
      </section>
    </div>

    <Card>
      <CardHeader>
        <CardTitle>开发者自助申请审核</CardTitle>
        <CardDescription>仅审核中申请可创建可用应用。驳回后，开发者将直接修改原申请并重新提交。</CardDescription>
      </CardHeader>
      <CardContent class="space-y-4">
        <article v-for="request in selfServiceRequests" :key="request.id" class="space-y-4 rounded-lg border p-4">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="space-y-1"><h3 class="font-semibold">{{ request.name }}</h3><p class="text-sm text-muted-foreground">{{ request.developer_name }} · 版本 {{ request.current_version }} · {{ request.status === 'rejected' ? `第 ${request.resubmission_count} 次重新提交` : '自助申请' }}</p></div>
            <Badge :variant="request.status === 'approved' ? 'default' : request.status === 'rejected' ? 'destructive' : 'secondary'">{{ requestStatusLabel(request.status) }}</Badge>
          </div>
          <p class="text-sm text-muted-foreground">{{ request.description || "未提供应用说明" }}</p>
          <div class="grid gap-3 text-sm sm:grid-cols-2"><p class="break-all text-muted-foreground">官网：{{ request.website_url }}</p><p class="break-all text-muted-foreground">隐私政策：{{ request.privacy_policy_url }}</p></div>
          <div class="flex flex-wrap gap-2"><Badge v-for="scope in request.requested_scopes" :key="scope" variant="outline">{{ scope }}</Badge></div>
          <p class="whitespace-pre-wrap text-sm text-muted-foreground">Windows 发行信息：{{ request.windows_release_info }}</p>
          <p class="whitespace-pre-wrap text-sm text-muted-foreground">使用场景：{{ request.use_case }}</p>
          <p v-if="request.review_note" class="rounded-md bg-muted p-3 text-sm text-muted-foreground">最近审核备注：{{ request.review_note }}</p>
          <div v-if="request.status === 'pending_review'" class="flex flex-wrap gap-2"><Button :disabled="busy === `request-approve:${request.id}`" @click="approveSelfServiceRequest(request)">{{ busy === `request-approve:${request.id}` ? "审核中…" : "审核通过并创建应用" }}</Button><Button variant="destructive" :disabled="busy === `request-reject:${request.id}`" @click="rejectSelfServiceRequest(request)">{{ busy === `request-reject:${request.id}` ? "处理中…" : "驳回申请" }}</Button></div>
        </article>
        <p v-if="selfServiceRequests.length === 0" class="py-8 text-center text-sm text-muted-foreground">暂无开发者自助申请。</p>
      </CardContent>
      <CardFooter class="text-sm text-muted-foreground">审核备注与可信验证开关使用页面上方“创建应用”区域的相应字段；驳回时审核备注必填。</CardFooter>
    </Card>
  </main>
</template>
