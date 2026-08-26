<script setup lang="ts">
import { DESKTOP_PLUGIN_CAPABILITIES, type DesktopPluginCapability, type DesktopPluginProjectDetail, type DesktopPluginStaticReviewReport, type DesktopPluginStaticReviewRun } from "@password-detective/api-contract";
import { computed, onMounted, ref } from "vue";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { apiRequest } from "../services/api";
import { listDeveloperApplications, type DeveloperApplication } from "../services/developerApplications";
import { createDeveloperPlugin, createPluginVersion, finalizePluginVersion, getPluginReviewReport, listDeveloperPlugins, registerPluginSigningKey, submitPluginVersion, uploadPluginPackage, withdrawPluginVersion, type SigningKeyRecord } from "../services/developerPlugins";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const projects = ref<DesktopPluginProjectDetail[]>([]);
const applications = ref<DeveloperApplication[]>([]);
const reviewReports = ref<Record<string, DesktopPluginStaticReviewReport>>({});
const busy = ref(false);
const error = ref("");
const success = ref("");
const file = ref<File | null>(null);
const generatedSigningKey = ref<SigningKeyRecord | null>(null);
const selectedCapabilities = ref<DesktopPluginCapability[]>(["ui:command"]);
const form = ref({ slug: "", name: "", summary: "", description: "", semver: "1.0.0", keyId: "", publicKey: "", linkedThirdPartyAppId: "none", currentPassword: "" });
const approvedApplications = computed(() => applications.value.filter(
  (application) => application.approved_application?.status === "approved",
));
const capabilityLabels: Record<DesktopPluginCapability, string> = {
  "ui:command": "用户界面命令",
  "ui:theme": "应用受控主题和背景",
  "storage:private": "私有存储",
  "file:read:selected": "读取用户选择的文件",
  "api:profile:read": "读取用户公开资料",
  "api:hash:read": "读取公开哈希资料",
  "api:verification:submit": "提交验证回执",
  "network:internet": "访问互联网",
  "secret:candidate:ephemeral": "访问临时候选秘密",
  "process:spawn": "创建子进程",
  "system:persistence": "系统持久化",
  "credential:read": "读取系统凭据",
};

function statusLabel(status: string): string {
  return { draft: "草稿", uploading: "上传中", quarantined: "待提交", review_queued: "等待自动审核", auto_review_running: "自动审核中", auto_review_failed: "自动审核未通过", manual_review_ready: "待人工审核", approved: "已批准", published: "已发布", rejected: "已驳回", yanked: "已下架", revoked: "已撤销" }[status] ?? status;
}

function latestReview(versionId: string): DesktopPluginStaticReviewRun | undefined {
  return reviewReports.value[versionId]?.runs[0];
}

async function withdraw(version: DesktopPluginProjectDetail["versions"][number]): Promise<void> {
  busy.value = true;
  error.value = "";
  try {
    await withdrawPluginVersion(auth.accessToken, version);
    success.value = "版本已撤回。";
    await load();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "版本撤回失败";
  } finally {
    busy.value = false;
  }
}

function toggleCapability(capability: DesktopPluginCapability, checked: boolean | "indeterminate"): void {
  selectedCapabilities.value = checked === true
    ? [...new Set([...selectedCapabilities.value, capability])]
    : selectedCapabilities.value.filter((value) => value !== capability);
}

async function load(): Promise<void> {
  try {
    const [pluginProjects, developerApplications] = await Promise.all([
      listDeveloperPlugins(auth.accessToken), listDeveloperApplications(auth.accessToken),
    ]);
    projects.value = pluginProjects;
    applications.value = developerApplications.items;
    const reports = await Promise.all(pluginProjects.flatMap((project) => project.versions).map(
      async (version) => [version.id, await getPluginReviewReport(auth.accessToken, version.id)] as const,
    ));
    reviewReports.value = Object.fromEntries(reports);
  }
  catch (caught) { error.value = caught instanceof Error ? caught.message : "无法加载插件项目"; }
}

async function createAndSubmit(): Promise<void> {
  if (!file.value) { error.value = "请选择 .pdpkg 插件包。"; return; }
  busy.value = true; error.value = ""; success.value = "";
  try {
    const project = await createDeveloperPlugin(auth.accessToken, {
      slug: form.value.slug, name: form.value.name, summary: form.value.summary,
      description: form.value.description, category: "development", tags: [],
      linked_third_party_app_id: form.value.linkedThirdPartyAppId === "none"
        ? null : form.value.linkedThirdPartyAppId,
    });
    const reauth = await apiRequest<{ reauth_token: string }>(
      "/me/security/reauthenticate",
      { method: "POST", body: JSON.stringify({ purpose: "desktop_plugin_signing_key", current_password: form.value.currentPassword }) },
      auth.accessToken,
    );
    const signingKey = generatedSigningKey.value ?? await registerPluginSigningKey(auth.accessToken, {
      key_id: form.value.keyId, public_key_base64: form.value.publicKey, reauth_token: reauth.reauth_token,
    });
    let version = await createPluginVersion(auth.accessToken, project.id, {
      semver: form.value.semver, signing_key_id: signingKey.id,
      requested_capabilities: selectedCapabilities.value,
    });
    await uploadPluginPackage(auth.accessToken, version.id, file.value);
    const refreshed = (await listDeveloperPlugins(auth.accessToken)).find((item) => item.id === project.id);
    version = refreshed?.versions[0] ?? version;
    version = await finalizePluginVersion(auth.accessToken, version);
    await submitPluginVersion(auth.accessToken, version);
    success.value = "插件版本已提交人工审核。";
    form.value.currentPassword = "";
    await load();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "插件提交失败";
  } finally { busy.value = false; }
}

async function generateSigningKey(): Promise<void> {
  busy.value = true;
  error.value = "";
  success.value = "";
  try {
    const reauth = await apiRequest<{ reauth_token: string }>(
      "/me/security/reauthenticate",
      { method: "POST", body: JSON.stringify({ purpose: "desktop_plugin_signing_key", current_password: form.value.currentPassword }) },
      auth.accessToken,
    );
    const signingKey = await registerPluginSigningKey(auth.accessToken, { reauth_token: reauth.reauth_token });
    if (!signingKey.private_key_base64) throw new Error("服务器未返回一次性私钥。");
    generatedSigningKey.value = signingKey;
    form.value.keyId = signingKey.key_id;
    form.value.publicKey = signingKey.public_key_base64;
    form.value.currentPassword = "";
    success.value = "Ed25519 密钥已生成。请使用一次性私钥完成本地签包。";
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "生成签名密钥失败";
  } finally {
    busy.value = false;
  }
}

function selectFile(event: Event): void {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null;
}

onMounted(load);
</script>

<template>
  <section class="mx-auto w-full max-w-6xl space-y-6 px-4 py-8">
    <header class="space-y-2"><p class="text-xs font-semibold text-primary">PLUGIN DEVELOPER CENTER</p><h1 class="text-3xl font-semibold">桌面插件开发者中心</h1><p class="text-sm text-muted-foreground">创建项目、生成或登记 Ed25519 密钥、上传不可变插件包并提交人工审核。</p></header>
    <Alert v-if="error" variant="destructive"><AlertTitle>操作未完成</AlertTitle><AlertDescription>{{ error }}</AlertDescription></Alert>
    <Alert v-if="success"><AlertTitle>提交成功</AlertTitle><AlertDescription>{{ success }}</AlertDescription></Alert>
    <div class="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(22rem,0.9fr)]">
      <Card><CardHeader><CardTitle>新建插件版本</CardTitle><CardDescription>插件包必须与项目 ID、版本和登记公钥完全一致。</CardDescription></CardHeader><CardContent class="space-y-4"><div class="grid gap-4 sm:grid-cols-2"><div class="space-y-2"><Label for="plugin-slug">插件 ID</Label><Input id="plugin-slug" v-model="form.slug" placeholder="com.example.plugin" /></div><div class="space-y-2"><Label for="plugin-name">插件名称</Label><Input id="plugin-name" v-model="form.name" /></div></div><div class="space-y-2"><Label for="plugin-summary">摘要</Label><Input id="plugin-summary" v-model="form.summary" /></div><div class="space-y-2"><Label for="plugin-description">说明</Label><Textarea id="plugin-description" v-model="form.description" rows="3" /></div><div class="grid gap-4 sm:grid-cols-2"><div class="space-y-2"><Label for="plugin-semver">版本</Label><Input id="plugin-semver" v-model="form.semver" /></div><div class="space-y-2"><Label for="plugin-key-id">签名密钥 ID</Label><Input id="plugin-key-id" v-model="form.keyId" /></div></div><div class="space-y-2"><Label for="plugin-public-key">Ed25519 公钥 Base64</Label><Input id="plugin-public-key" v-model="form.publicKey" /></div><div class="flex flex-wrap gap-2"><Button variant="outline" :disabled="busy" @click="generateSigningKey">生成 Ed25519 密钥</Button></div><div v-if="generatedSigningKey" class="space-y-2 rounded-md border p-3"><Label for="generated-private-key">一次性 Ed25519 私钥 Base64</Label><Textarea id="generated-private-key" :model-value="generatedSigningKey.private_key_base64 ?? ''" readonly rows="3" /></div><div class="space-y-2"><Label for="plugin-linked-application">关联第三方应用</Label><Select v-model="form.linkedThirdPartyAppId"><SelectTrigger id="plugin-linked-application"><SelectValue placeholder="不关联" /></SelectTrigger><SelectContent><SelectItem value="none">不关联</SelectItem><SelectItem v-for="application in approvedApplications" :key="application.approved_application!.id" :value="application.approved_application!.id">{{ application.name }} · {{ application.approved_application!.approved_scopes.join('、') }}</SelectItem></SelectContent></Select></div><fieldset class="space-y-3"><legend class="text-sm font-medium">申请权限</legend><div class="grid gap-2 sm:grid-cols-2"><div v-for="capability in DESKTOP_PLUGIN_CAPABILITIES" :key="capability" class="flex items-center gap-3 rounded-md border p-3"><Checkbox :id="`developer-plugin-${capability}`" :checked="selectedCapabilities.includes(capability)" @update:checked="toggleCapability(capability, $event)" /><Label :for="`developer-plugin-${capability}`"><span class="text-xs">{{ capabilityLabels[capability] }}</span></Label></div></div></fieldset><div class="space-y-2"><Label for="plugin-package">插件包</Label><Input id="plugin-package" type="file" accept=".pdpkg" @change="selectFile" /><p class="text-xs text-muted-foreground">{{ file?.name || "尚未选择文件" }}</p></div><div class="space-y-2"><Label for="plugin-current-password">当前密码</Label><Input id="plugin-current-password" v-model="form.currentPassword" type="password" autocomplete="current-password" /></div></CardContent><CardFooter><Button :disabled="busy" @click="createAndSubmit">{{ busy ? "提交中…" : "创建、上传并提交审核" }}</Button></CardFooter></Card>
      <Card><CardHeader><CardTitle>我的插件项目</CardTitle><CardDescription>版本状态、自动审核报告和已批准权限。</CardDescription></CardHeader><CardContent class="space-y-3"><article v-for="project in projects" :key="project.id" class="space-y-3 rounded-md border p-4"><div class="flex items-start justify-between gap-3"><div><h2 class="font-medium">{{ project.name }}</h2><code class="text-xs text-muted-foreground">{{ project.slug }}</code></div><Badge>{{ project.status }}</Badge></div><div v-for="version in project.versions" :key="version.id" class="rounded-md bg-muted p-3 text-sm"><div class="flex justify-between gap-3"><strong>{{ version.semver }}</strong><div class="flex items-center gap-2"><Badge variant="outline">{{ statusLabel(version.status) }}</Badge><Button v-if="['quarantined','review_queued','auto_review_running','auto_review_failed','manual_review_ready','rejected'].includes(version.status)" size="sm" variant="ghost" :disabled="busy" @click="withdraw(version)">撤回</Button></div></div><div v-if="latestReview(version.id)" class="mt-3 space-y-2 border-t pt-3"><div class="flex items-center justify-between gap-2"><span class="text-xs font-medium">自动审核 {{ latestReview(version.id)?.policy_version }}</span><Badge :variant="latestReview(version.id)?.status === 'passed' ? 'default' : 'destructive'">{{ latestReview(version.id)?.status }}</Badge></div><div v-for="finding in latestReview(version.id)?.findings" :key="finding.id" class="rounded-md border bg-background p-2"><div class="flex items-center gap-2"><code class="text-xs">{{ finding.rule_id }}</code><Badge variant="outline">{{ finding.severity }}</Badge></div><p class="mt-1 text-xs">{{ finding.title }}</p><p class="text-xs text-muted-foreground">{{ finding.detail }}</p></div></div><p v-if="version.approved_capabilities.length" class="mt-2 text-xs text-muted-foreground">批准权限：{{ version.approved_capabilities.join('、') }}</p></div></article><p v-if="projects.length === 0" class="text-sm text-muted-foreground">尚无插件项目。</p></CardContent></Card>
    </div>
  </section>
</template>
