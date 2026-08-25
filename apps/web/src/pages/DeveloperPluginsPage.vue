<script setup lang="ts">
import { DESKTOP_PLUGIN_CAPABILITIES, type DesktopPluginCapability, type DesktopPluginProjectDetail } from "@password-detective/api-contract";
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
import { createDeveloperPlugin, createPluginVersion, finalizePluginVersion, listDeveloperPlugins, registerPluginSigningKey, submitPluginVersion, uploadPluginPackage } from "../services/developerPlugins";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const projects = ref<DesktopPluginProjectDetail[]>([]);
const applications = ref<DeveloperApplication[]>([]);
const busy = ref(false);
const error = ref("");
const success = ref("");
const file = ref<File | null>(null);
const selectedCapabilities = ref<DesktopPluginCapability[]>(["ui:command"]);
const form = ref({ slug: "", name: "", summary: "", description: "", semver: "1.0.0", keyId: "", publicKey: "", linkedThirdPartyAppId: "none", currentPassword: "" });
const approvedApplications = computed(() => applications.value.filter(
  (application) => application.approved_application?.status === "approved",
));

function statusLabel(status: string): string {
  return { draft: "草稿", uploading: "上传中", quarantined: "待提交", review_queued: "审核中", approved: "已批准", published: "已发布", rejected: "已驳回", yanked: "已下架", revoked: "已撤销" }[status] ?? status;
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
    const signingKey = await registerPluginSigningKey(auth.accessToken, {
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

function selectFile(event: Event): void {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null;
}

onMounted(load);
</script>

<template>
  <section class="mx-auto w-full max-w-6xl space-y-6 px-4 py-8">
    <header class="space-y-2"><p class="text-xs font-semibold text-primary">PLUGIN DEVELOPER CENTER</p><h1 class="text-3xl font-semibold">桌面插件开发者中心</h1><p class="text-sm text-muted-foreground">创建项目、登记 Ed25519 公钥、上传不可变插件包并提交人工审核。</p></header>
    <Alert v-if="error" variant="destructive"><AlertTitle>操作未完成</AlertTitle><AlertDescription>{{ error }}</AlertDescription></Alert>
    <Alert v-if="success"><AlertTitle>提交成功</AlertTitle><AlertDescription>{{ success }}</AlertDescription></Alert>
    <div class="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(22rem,0.9fr)]">
      <Card><CardHeader><CardTitle>新建插件版本</CardTitle><CardDescription>插件包必须与项目 ID、版本和登记公钥完全一致。</CardDescription></CardHeader><CardContent class="space-y-4"><div class="grid gap-4 sm:grid-cols-2"><div class="space-y-2"><Label for="plugin-slug">插件 ID</Label><Input id="plugin-slug" v-model="form.slug" placeholder="com.example.plugin" /></div><div class="space-y-2"><Label for="plugin-name">插件名称</Label><Input id="plugin-name" v-model="form.name" /></div></div><div class="space-y-2"><Label for="plugin-summary">摘要</Label><Input id="plugin-summary" v-model="form.summary" /></div><div class="space-y-2"><Label for="plugin-description">说明</Label><Textarea id="plugin-description" v-model="form.description" rows="3" /></div><div class="grid gap-4 sm:grid-cols-2"><div class="space-y-2"><Label for="plugin-semver">版本</Label><Input id="plugin-semver" v-model="form.semver" /></div><div class="space-y-2"><Label for="plugin-key-id">签名密钥 ID</Label><Input id="plugin-key-id" v-model="form.keyId" /></div></div><div class="space-y-2"><Label for="plugin-public-key">Ed25519 公钥 Base64</Label><Input id="plugin-public-key" v-model="form.publicKey" /></div><div class="space-y-2"><Label for="plugin-linked-application">关联第三方应用</Label><Select v-model="form.linkedThirdPartyAppId"><SelectTrigger id="plugin-linked-application"><SelectValue placeholder="不关联" /></SelectTrigger><SelectContent><SelectItem value="none">不关联</SelectItem><SelectItem v-for="application in approvedApplications" :key="application.approved_application!.id" :value="application.approved_application!.id">{{ application.name }} · {{ application.approved_application!.approved_scopes.join('、') }}</SelectItem></SelectContent></Select></div><fieldset class="space-y-3"><legend class="text-sm font-medium">申请权限</legend><div class="grid gap-2 sm:grid-cols-2"><div v-for="capability in DESKTOP_PLUGIN_CAPABILITIES" :key="capability" class="flex items-center gap-3 rounded-md border p-3"><Checkbox :id="`developer-plugin-${capability}`" :checked="selectedCapabilities.includes(capability)" @update:checked="toggleCapability(capability, $event)" /><Label :for="`developer-plugin-${capability}`"><code class="text-xs">{{ capability }}</code></Label></div></div></fieldset><div class="space-y-2"><Label for="plugin-package">插件包</Label><Input id="plugin-package" type="file" accept=".pdpkg" @change="selectFile" /><p class="text-xs text-muted-foreground">{{ file?.name || "尚未选择文件" }}</p></div><div class="space-y-2"><Label for="plugin-current-password">当前密码</Label><Input id="plugin-current-password" v-model="form.currentPassword" type="password" autocomplete="current-password" /></div></CardContent><CardFooter><Button :disabled="busy" @click="createAndSubmit">{{ busy ? "提交中…" : "创建、上传并提交审核" }}</Button></CardFooter></Card>
      <Card><CardHeader><CardTitle>我的插件项目</CardTitle><CardDescription>版本状态、审核进度和已批准权限。</CardDescription></CardHeader><CardContent class="space-y-3"><article v-for="project in projects" :key="project.id" class="space-y-3 rounded-md border p-4"><div class="flex items-start justify-between gap-3"><div><h2 class="font-medium">{{ project.name }}</h2><code class="text-xs text-muted-foreground">{{ project.slug }}</code></div><Badge>{{ project.status }}</Badge></div><div v-for="version in project.versions" :key="version.id" class="rounded-md bg-muted p-3 text-sm"><div class="flex justify-between"><strong>{{ version.semver }}</strong><Badge variant="outline">{{ statusLabel(version.status) }}</Badge></div><p v-if="version.approved_capabilities.length" class="mt-2 text-xs text-muted-foreground">批准权限：{{ version.approved_capabilities.join('、') }}</p></div></article><p v-if="projects.length === 0" class="text-sm text-muted-foreground">尚无插件项目。</p></CardContent></Card>
    </div>
  </section>
</template>
