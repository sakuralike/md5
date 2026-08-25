<script setup lang="ts">
import { THIRD_PARTY_REQUESTABLE_SCOPE_OPTIONS } from "@password-detective/api-contract";
import { computed, onMounted, onServerPrefetch, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  createDeveloperApplication,
  listDeveloperApplications,
  submitDeveloperApplication,
  type DeveloperApplication,
  type DeveloperApplicationForm,
  type DeveloperApplicationStatus,
  updateDeveloperApplication,
} from "../services/developerApplications";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();
const applications = ref<DeveloperApplication[]>([]);
const editingId = ref<string | null>(null);
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const success = ref("");
const form = ref<DeveloperApplicationForm>({
  name: "",
  developer_name: "",
  description: "",
  website_url: "",
  privacy_policy_url: "",
  redirect_uris: [],
  scopes: ["profile:read"],
  windows_release_info: "Windows 桌面端，支持本地验证与哈希提交。",
  use_case: "",
});
const redirectUrisText = ref("");
const selectableScopes = THIRD_PARTY_REQUESTABLE_SCOPE_OPTIONS;

const editingApplication = computed(() =>
  applications.value.find((application) => application.id === editingId.value) ?? null,
);
const isApplyPage = computed(() => route.path === "/developer/apply");

function messageFrom(caught: unknown, fallback: string): string {
  return caught instanceof Error ? caught.message : fallback;
}

function splitLines(value: string): string[] {
  return [...new Set(value.split(/\r?\n|,/).map((item) => item.trim()).filter(Boolean))];
}

function updateScopeSelection(scope: string, checked: boolean | "indeterminate"): void {
  form.value.scopes = checked === true
    ? [...new Set([...form.value.scopes, scope])]
    : form.value.scopes.filter((selectedScope) => selectedScope !== scope);
}

function statusLabel(status: DeveloperApplicationStatus): string {
  return { draft: "草稿", pending_review: "审核中", rejected: "已驳回", approved: "已通过" }[status];
}

function resetForm(): void {
  editingId.value = null;
  form.value = {
    name: "",
    developer_name: auth.user?.username ?? "",
    description: "",
    website_url: "",
    privacy_policy_url: "",
    redirect_uris: [],
    scopes: ["profile:read"],
    windows_release_info: "Windows 桌面端，支持本地验证与哈希提交。",
    use_case: "",
  };
  redirectUrisText.value = "";
}

function populateForm(application: DeveloperApplication): void {
  editingId.value = application.id;
  form.value = {
    name: application.name,
    developer_name: application.developer_name,
    description: application.description,
    website_url: application.website_url,
    privacy_policy_url: application.privacy_policy_url,
    redirect_uris: application.redirect_uris,
    scopes: application.requested_scopes,
    windows_release_info: application.windows_release_info,
    use_case: application.use_case,
  };
  redirectUrisText.value = application.redirect_uris.join("\n");
  success.value = "已载入申请，可直接修改后保存或重新提交。";
}

function startEditing(application: DeveloperApplication): void {
  populateForm(application);
  void router.push({ path: "/developer/apply", query: { edit: application.id } });
}

function syncFormLists(): boolean {
  form.value.redirect_uris = splitLines(redirectUrisText.value);
  if (form.value.redirect_uris.length === 0 || form.value.scopes.length === 0) {
    error.value = "请至少填写一个回调地址和一个申请 Scope。";
    return false;
  }
  return true;
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    applications.value = (await listDeveloperApplications(auth.accessToken)).items;
    const requestedId = typeof route.query.edit === "string" ? route.query.edit : null;
    const requestedApplication = applications.value.find((application) => application.id === requestedId);
    if (requestedApplication) populateForm(requestedApplication);
  } catch (caught) {
    error.value = messageFrom(caught, "无法加载开发者申请记录");
  } finally {
    loading.value = false;
  }
}

async function saveDraft(): Promise<DeveloperApplication | null> {
  if (!syncFormLists()) return null;
  saving.value = true;
  error.value = "";
  success.value = "";
  try {
    const saved = editingId.value
      ? await updateDeveloperApplication(editingId.value, form.value, auth.accessToken)
      : await createDeveloperApplication(form.value, auth.accessToken);
    editingId.value = saved.id;
    await load();
    success.value = "申请草稿已保存。";
    return saved;
  } catch (caught) {
    error.value = messageFrom(caught, "保存申请草稿失败");
    return null;
  } finally {
    saving.value = false;
  }
}

async function submitForReview(): Promise<void> {
  const saved = await saveDraft();
  if (!saved) return;
  saving.value = true;
  error.value = "";
  try {
    const submitted = await submitDeveloperApplication(saved.id, auth.accessToken);
    await load();
    editingId.value = submitted.id;
    success.value = "申请已提交管理员审核。审核通过后才会创建可使用的第三方应用。";
  } catch (caught) {
    error.value = messageFrom(caught, "提交审核失败");
  } finally {
    saving.value = false;
  }
}

watch(
  () => route.query.edit,
  (requestedId) => {
    const application = typeof requestedId === "string"
      ? applications.value.find((item) => item.id === requestedId)
      : null;
    if (application) populateForm(application);
  },
);

onMounted(() => {
  resetForm();
  void load();
});
onServerPrefetch(load);
</script>

<template>
  <section class="mx-auto w-full max-w-6xl space-y-6 px-4 py-8">
    <header class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div class="space-y-2">
        <p class="text-xs font-semibold uppercase tracking-[0.22em] text-primary">Developer center</p>
        <h1 class="text-3xl font-semibold tracking-tight">{{ isApplyPage ? "开发者应用申请" : "我的开发者应用" }}</h1>
        <p class="max-w-3xl text-sm leading-6 text-muted-foreground">{{ isApplyPage ? "创建草稿、提交审核；被驳回后可在原申请中修改并重新提交。只有管理员审核通过，系统才会创建可用的第三方桌面应用。" : "查看申请进度、审核反馈和已创建的 Client ID；需要新建或修改申请时进入申请页面。" }}</p>
      </div>
      <div class="flex flex-wrap gap-2"><Button as-child variant="outline"><RouterLink to="/developer/plugins">插件开发者中心</RouterLink></Button><Button v-if="!isApplyPage" as-child><RouterLink to="/developer/apply">新建申请</RouterLink></Button><Button variant="outline" :disabled="loading" @click="load">{{ loading ? "刷新中…" : "刷新记录" }}</Button></div>
    </header>

    <Alert v-if="error" variant="destructive"><AlertTitle>操作未完成</AlertTitle><AlertDescription>{{ error }}</AlertDescription></Alert>
    <Alert v-if="success"><AlertTitle>操作成功</AlertTitle><AlertDescription>{{ success }}</AlertDescription></Alert>

    <div class="grid gap-6" :class="isApplyPage ? 'xl:grid-cols-[minmax(0,1.2fr)_minmax(20rem,0.8fr)]' : 'max-w-3xl'">
      <Card v-if="isApplyPage">
        <CardHeader>
          <CardTitle>{{ editingId ? "编辑申请" : "新建申请" }}</CardTitle>
          <CardDescription>请填写真实的桌面端发行信息与隐私政策地址。申请内容会保留版本和审核记录。</CardDescription>
        </CardHeader>
        <CardContent class="space-y-4">
          <div class="grid gap-4 sm:grid-cols-2">
            <div class="space-y-2"><Label for="developer-app-name">应用名称</Label><Input id="developer-app-name" v-model="form.name" maxlength="128" /></div>
            <div class="space-y-2"><Label for="developer-app-developer">开发者名称</Label><Input id="developer-app-developer" v-model="form.developer_name" maxlength="128" /></div>
          </div>
          <div class="space-y-2"><Label for="developer-app-description">应用说明</Label><Textarea id="developer-app-description" v-model="form.description" rows="3" /></div>
          <div class="grid gap-4 sm:grid-cols-2">
            <div class="space-y-2"><Label for="developer-app-website">官网地址</Label><Input id="developer-app-website" v-model="form.website_url" type="url" placeholder="https://example.com" /></div>
            <div class="space-y-2"><Label for="developer-app-privacy">隐私政策地址</Label><Input id="developer-app-privacy" v-model="form.privacy_policy_url" type="url" placeholder="https://example.com/privacy" /></div>
          </div>
          <div class="space-y-2"><Label for="developer-app-redirects">OAuth 回调地址（每行一个）</Label><Textarea id="developer-app-redirects" v-model="redirectUrisText" rows="3" placeholder="https://example.com/oauth/callback" /></div>
          <fieldset class="space-y-3"><legend class="text-sm font-medium leading-none">申请 Scope</legend><p class="text-xs text-muted-foreground">请手动勾选所需权限。可信直入总哈希池不在此处申请，仅能由管理员审核后单独授予。</p><div class="grid gap-3 sm:grid-cols-2"><div v-for="option in selectableScopes" :key="option.value" class="flex gap-3 rounded-lg border p-3"><Checkbox :id="`developer-app-scope-${option.value}`" :checked="form.scopes.includes(option.value)" @update:checked="updateScopeSelection(option.value, $event)" /><Label :for="`developer-app-scope-${option.value}`" class="grid cursor-pointer gap-1 leading-snug"><span class="font-medium text-foreground">{{ option.label }}</span><code class="text-xs text-muted-foreground">{{ option.value }}</code><span class="text-xs font-normal text-muted-foreground">{{ option.description }}</span></Label></div></div></fieldset>
          <div class="space-y-2"><Label for="developer-app-release">Windows 桌面端发行信息</Label><Textarea id="developer-app-release" v-model="form.windows_release_info" rows="3" /></div>
          <div class="space-y-2"><Label for="developer-app-use-case">使用场景与数据处理说明</Label><Textarea id="developer-app-use-case" v-model="form.use_case" rows="4" /></div>
        </CardContent>
        <CardFooter class="flex flex-wrap gap-2">
          <Button :disabled="saving" @click="saveDraft">{{ saving ? "处理中…" : "保存草稿" }}</Button>
          <Button variant="secondary" :disabled="saving || editingApplication?.status === 'approved'" @click="submitForReview">提交审核</Button>
          <Button v-if="editingId" variant="ghost" :disabled="saving" @click="resetForm">新建另一份申请</Button>
        </CardFooter>
      </Card>

      <Card>
        <CardHeader><CardTitle>我的申请</CardTitle><CardDescription>审核状态及管理员反馈。<RouterLink v-if="isApplyPage" class="ml-2 text-primary underline-offset-4 hover:underline" to="/developer/applications">返回管理页</RouterLink></CardDescription></CardHeader>
        <CardContent class="space-y-3">
          <div v-if="loading" class="h-28 animate-pulse rounded-lg bg-muted" />
          <div v-else-if="applications.length === 0" class="rounded-lg border border-dashed p-5 text-sm text-muted-foreground">尚无申请记录。保存草稿后可随时补充内容，再提交审核。</div>
          <article v-for="application in applications" :key="application.id" class="space-y-3 rounded-lg border p-4">
            <div class="flex flex-wrap items-start justify-between gap-2"><div><h2 class="font-medium">{{ application.name }}</h2><p class="text-xs text-muted-foreground">版本 {{ application.current_version }} · {{ application.developer_name }}</p></div><Badge :variant="application.status === 'approved' ? 'default' : application.status === 'rejected' ? 'destructive' : 'secondary'">{{ statusLabel(application.status) }}</Badge></div>
            <p v-if="application.review_note" class="text-sm text-muted-foreground">审核反馈：{{ application.review_note }}</p>
            <div v-if="application.approved_application" class="rounded-md bg-muted p-3 text-xs text-muted-foreground">应用已创建。Client ID：<span class="font-mono text-foreground">{{ application.approved_application.client_id }}</span></div>
            <div class="flex flex-wrap gap-2"><Button size="sm" variant="outline" :disabled="application.status === 'approved'" @click="startEditing(application)">{{ application.status === 'rejected' ? "修改并重新提交" : "编辑" }}</Button><Button v-if="application.status === 'draft'" size="sm" @click="startEditing(application)">继续填写</Button></div>
          </article>
        </CardContent>
        <CardFooter><Button as-child variant="ghost"><RouterLink to="/account/authorized-applications">查看我已授权的应用</RouterLink></Button></CardFooter>
      </Card>
    </div>
  </section>
</template>
