<script setup lang="ts">
import { createClientId } from "@/lib/clientId";
import {
  ApiError,
  type EmailDeliverySettings,
  type OperationalSettingsSnapshot,
  type UserLevelDefinition,
} from "@password-detective/api-contract";
import {
  CheckCircle2,
  Globe2,
  ImageUp,
  MailCheck,
  Navigation,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Send,
  Server,
  Settings2,
  Trash2,
} from "lucide-vue-next";
import { onMounted, ref } from "vue";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  getCurrentSettings,
  getEmailDeliverySettings,
  saveCurrentSettings,
  sendEmailDeliveryTest,
  uploadSiteLogo,
} from "../services/settings";
import { useAdminAuthStore } from "../stores/auth";

const defaultUserLevels: UserLevelDefinition[] = [
  { code: "rookie", name: "新手侦探", description: "完成注册并开始参与社区协作。", min_growth_points: 0, daily_reveal_quota: 20, can_submit: true },
  { code: "apprentice", name: "见习侦探", description: "持续贡献有效档案或验证反馈。", min_growth_points: 100, daily_reveal_quota: 30, can_submit: true },
  { code: "senior", name: "资深侦探", description: "具备稳定、长期的有效社区贡献。", min_growth_points: 500, daily_reveal_quota: 50, can_submit: true },
  { code: "expert", name: "专家侦探", description: "在贡献和验证活动中保持高质量表现。", min_growth_points: 1500, daily_reveal_quota: 75, can_submit: true },
  { code: "chief", name: "首席侦探", description: "达到社区成长体系的最高长期贡献等级。", min_growth_points: 5000, daily_reveal_quota: 100, can_submit: true },
];

const defaultSnapshot: OperationalSettingsSnapshot = {
  site_name: "密码侦探社",
  site_logo_url: "",
  site_navigation: [
    { label: "首页", path: "/", enabled: true, requires_auth: false },
    { label: "社区", path: "/community", enabled: true, requires_auth: false },
  ],
  daily_reveal_quota: 20,
  reauthentication_ttl_minutes: 5,
  privacy_deletion_grace_hours: 72,
  desktop_min_client_version: "1.0.0",
  desktop_update_download_cache_seconds: 3600,
  user_levels: defaultUserLevels,
};

const auth = useAdminAuthStore();
const form = ref<OperationalSettingsSnapshot>(structuredClone(defaultSnapshot));
const baselineSnapshot = ref<OperationalSettingsSnapshot>(structuredClone(defaultSnapshot));
const loading = ref(false);
const mutationBusy = ref(false);
const error = ref("");
const success = ref("");
const emailSettings = ref<EmailDeliverySettings | null>(null);
const emailLoading = ref(false);
const emailTestBusy = ref(false);
const emailRecipient = ref("");
const emailMessage = ref("");
const emailError = ref("");
const logoUploadBusy = ref(false);
const logoUploadError = ref("");
const logoUploadMessage = ref("");

function describeError(value: unknown): string {
  return value instanceof ApiError ? value.message : "请求失败，请稍后重试";
}

function resetMessages(): void {
  error.value = "";
  success.value = "";
}

function useSnapshot(snapshot: OperationalSettingsSnapshot): void {
  const persisted = structuredClone(snapshot);
  baselineSnapshot.value = persisted;
  form.value = structuredClone(persisted);
}

function resetCurrentEdits(): void {
  useSnapshot(baselineSnapshot.value);
  resetMessages();
  logoUploadError.value = "";
  logoUploadMessage.value = "";
  success.value = "已恢复到当前已保存的系统设置。";
}

function normalizedSnapshot(): OperationalSettingsSnapshot {
  const snapshot: OperationalSettingsSnapshot = {
    site_name: form.value.site_name.trim(),
    site_logo_url: form.value.site_logo_url.trim(),
    site_navigation: form.value.site_navigation.map((item) => ({ ...item })),
    daily_reveal_quota: Number(form.value.daily_reveal_quota),
    reauthentication_ttl_minutes: Number(form.value.reauthentication_ttl_minutes),
    privacy_deletion_grace_hours: Number(form.value.privacy_deletion_grace_hours),
    desktop_min_client_version: form.value.desktop_min_client_version.trim(),
    desktop_update_download_cache_seconds: Number(form.value.desktop_update_download_cache_seconds),
    user_levels: form.value.user_levels.map((level) => ({ ...level })),
  };
  snapshot.user_levels.sort((left, right) => left.min_growth_points - right.min_growth_points);
  snapshot.user_levels[0].min_growth_points = 0;
  return snapshot;
}

function addNavigationItem(): void {
  if (form.value.site_navigation.length >= 8) return;
  const sequence = form.value.site_navigation.length + 1;
  form.value.site_navigation.push({ label: `导航 ${sequence}`, path: `/page-${sequence}`, enabled: true, requires_auth: false });
}

function removeNavigationItem(index: number): void {
  if (form.value.site_navigation.length > 1) form.value.site_navigation.splice(index, 1);
}


async function handleLogoUpload(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  logoUploadError.value = "";
  logoUploadMessage.value = "";
  if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
    logoUploadError.value = "Logo 仅支持 PNG、JPEG 或 WebP 图片";
    return;
  }
  if (file.size > 2 * 1024 * 1024) {
    logoUploadError.value = "Logo 图片不能超过 2 MB";
    return;
  }
  logoUploadBusy.value = true;
  try {
    const uploaded = await uploadSiteLogo(file, auth.accessToken);
    form.value.site_logo_url = uploaded.url;
    logoUploadMessage.value = "图片已上传并写入当前配置表单，点击保存设置后立即生效。";
  } catch (value) {
    logoUploadError.value = describeError(value);
  } finally {
    logoUploadBusy.value = false;
  }
}

async function saveSettings(): Promise<void> {
  resetMessages();
  mutationBusy.value = true;
  try {
    const response = await saveCurrentSettings(normalizedSnapshot(), auth.accessToken, createClientId());
    useSnapshot(response.settings);
    success.value = "系统设置已直接保存并立即生效。";
  } catch (value) {
    error.value = describeError(value);
  } finally {
    mutationBusy.value = false;
  }
}

async function loadEmailSettings(): Promise<void> {
  emailLoading.value = true;
  emailError.value = "";
  try {
    emailSettings.value = await getEmailDeliverySettings(auth.accessToken);
  } catch (value) {
    emailError.value = describeError(value);
  } finally {
    emailLoading.value = false;
  }
}

async function sendEmailTest(): Promise<void> {
  emailError.value = "";
  emailMessage.value = "";
  emailTestBusy.value = true;
  try {
    const response = await sendEmailDeliveryTest(emailRecipient.value.trim(), auth.accessToken);
    emailMessage.value = response.message;
  } catch (value) {
    emailError.value = describeError(value);
  } finally {
    emailTestBusy.value = false;
  }
}

async function refreshPage(): Promise<void> {
  loading.value = true;
  resetMessages();
  try {
    const response = await getCurrentSettings(auth.accessToken);
    useSnapshot(response.settings);
    await loadEmailSettings();
  } catch (value) {
    error.value = describeError(value);
  } finally {
    loading.value = false;
  }
}

onMounted(refreshPage);
</script>

<template>
  <section class="space-y-6">
    <header class="glass-panel overflow-hidden p-6 sm:p-8">
      <div class="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div class="max-w-3xl space-y-3">
          <div class="flex items-center gap-2 text-sm font-medium text-primary"><Settings2 class="size-4" />后台设置</div>
          <h1 class="text-3xl font-semibold tracking-tight text-foreground">系统配置工作台</h1>
          <p class="text-sm leading-6 text-muted-foreground">直接保存设置，当前配置将立即生效；不提供版本历史、差异预览或回滚快照。</p>
        </div>
        <Button variant="outline" :disabled="loading" @click="refreshPage"><RefreshCw class="mr-2 size-4" />刷新设置</Button>
      </div>
    </header>

    <div v-if="error" class="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">{{ error }}</div>
    <div v-if="success" class="rounded-xl border border-primary/30 bg-primary/10 px-4 py-3 text-sm text-foreground"><CheckCircle2 class="mr-2 inline size-4" />{{ success }}</div>

    <div class="min-w-0 space-y-6" data-layout="stacked-settings-regions">
      <section id="site-brand" class="glass-panel scroll-mt-28 p-6">
        <div class="mb-5"><h2 class="flex items-center gap-2 text-lg font-semibold text-foreground"><Globe2 class="size-5 text-primary" />站点品牌</h2><p class="mt-1 text-sm text-muted-foreground">保存后站点名称、Logo 和导航会立即使用当前设置。</p></div>
        <div class="grid gap-4 sm:grid-cols-2">
          <div class="space-y-2"><Label for="site-name">站点名称</Label><Input id="site-name" v-model="form.site_name" maxlength="32" /></div>
          <div class="space-y-2"><Label for="site-logo-url">Logo 地址</Label><Input id="site-logo-url" v-model="form.site_logo_url" placeholder="/api/v1/site/assets/logo/..." /></div>
        </div>
        <div class="mt-4 rounded-xl border border-dashed border-border p-4">
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><div><p class="flex items-center gap-2 text-sm font-medium text-foreground"><ImageUp class="size-4 text-primary" />上传 Logo 图片</p><p class="mt-1 text-xs text-muted-foreground">支持 PNG、JPEG、WebP，最大 2 MB。</p></div><Input aria-label="上传 Logo 图片" type="file" accept="image/png,image/jpeg,image/webp" class="max-w-xs" :disabled="logoUploadBusy" @change="handleLogoUpload" /></div>
          <p v-if="logoUploadMessage" class="mt-3 text-sm text-primary">{{ logoUploadMessage }}</p><p v-if="logoUploadError" class="mt-3 text-sm text-destructive">{{ logoUploadError }}</p>
        </div>
      </section>

      <section id="site-navigation" class="glass-panel scroll-mt-28 p-6">
        <div class="mb-5 flex items-start justify-between gap-4"><div><h2 class="flex items-center gap-2 text-lg font-semibold text-foreground"><Navigation class="size-5 text-primary" />站点导航</h2><p class="mt-1 text-sm text-muted-foreground">至少保留一个已启用的站内导航项。</p></div><Button type="button" variant="outline" :disabled="form.site_navigation.length >= 8" @click="addNavigationItem"><Plus class="mr-2 size-4" />新增导航</Button></div>
        <div class="space-y-3"><div v-for="(item, index) in form.site_navigation" :key="`${item.path}-${index}`" class="rounded-xl border border-border p-4"><div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><div class="space-y-2"><Label :for="`navigation-label-${index}`">名称</Label><Input :id="`navigation-label-${index}`" v-model="item.label" /></div><div class="space-y-2"><Label :for="`navigation-path-${index}`">路径</Label><Input :id="`navigation-path-${index}`" v-model="item.path" /></div><div class="flex items-end gap-4 pb-2"><Label class="flex items-center gap-2"><Checkbox :model-value="item.enabled" @update:model-value="item.enabled = $event === true" />启用</Label><Label class="flex items-center gap-2"><Checkbox :model-value="item.requires_auth" @update:model-value="item.requires_auth = $event === true" />登录后可见</Label></div><div class="flex items-end justify-end"><Button type="button" variant="ghost" :disabled="form.site_navigation.length <= 1" @click="removeNavigationItem(index)"><Trash2 class="mr-2 size-4" />删除</Button></div></div></div></div>
      </section>

      <section id="operational-policy" class="glass-panel scroll-mt-28 p-6">
        <div class="mb-5"><h2 class="flex items-center gap-2 text-lg font-semibold text-foreground"><Server class="size-5 text-primary" />运行参数</h2><p class="mt-1 text-sm text-muted-foreground">这些设置会在保存后直接更新运行时配置。</p></div>
        <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"><div class="space-y-2"><Label for="daily-quota">每日明文查看配额</Label><Input id="daily-quota" v-model.number="form.daily_reveal_quota" type="number" min="1" max="1000" /></div><div class="space-y-2"><Label for="reauth-ttl">再认证有效期（分钟）</Label><Input id="reauth-ttl" v-model.number="form.reauthentication_ttl_minutes" type="number" min="1" max="15" /></div><div class="space-y-2"><Label for="deletion-grace">账号删除宽限期（小时）</Label><Input id="deletion-grace" v-model.number="form.privacy_deletion_grace_hours" type="number" min="1" max="720" /></div><div class="space-y-2"><Label for="min-client">桌面端最低版本</Label><Input id="min-client" v-model="form.desktop_min_client_version" placeholder="1.0.0" /></div><div class="space-y-2"><Label for="download-cache">升级下载缓存（秒）</Label><Input id="download-cache" v-model.number="form.desktop_update_download_cache_seconds" type="number" min="60" max="31536000" /></div></div>
      </section>

      <section id="email-delivery" class="glass-panel scroll-mt-28 p-6">
        <div class="mb-5"><h2 class="flex items-center gap-2 text-lg font-semibold text-foreground"><MailCheck class="size-5 text-primary" />SMTP 邮件投递</h2><p class="mt-1 text-sm text-muted-foreground">邮件服务凭据由服务器环境变量管理，此处仅显示状态与发送测试邮件。</p></div>
        <div v-if="emailLoading" class="text-sm text-muted-foreground">正在加载邮件配置…</div><div v-else-if="emailSettings" class="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-3"><p><span class="text-muted-foreground">服务器：</span>{{ emailSettings.smtp_host }}:{{ emailSettings.smtp_port }}</p><p><span class="text-muted-foreground">发件地址：</span>{{ emailSettings.sender_email }}</p><p><span class="text-muted-foreground">投递状态：</span>{{ emailSettings.enabled ? "已启用" : "未启用" }}</p></div>
        <div class="mt-5 flex flex-col gap-3 sm:flex-row"><Input v-model="emailRecipient" type="email" placeholder="recipient@synthetic.example.com" aria-label="测试邮件收件人" /><Button :disabled="emailTestBusy || !emailRecipient.trim()" @click="sendEmailTest"><Send class="mr-2 size-4" />发送测试邮件</Button></div><p v-if="emailMessage" class="mt-3 text-sm text-primary">{{ emailMessage }}</p><p v-if="emailError" class="mt-3 text-sm text-destructive">{{ emailError }}</p>
      </section>

      <section class="glass-panel flex flex-wrap justify-end gap-3 p-6"><Button type="button" variant="outline" :disabled="loading || mutationBusy" @click="resetCurrentEdits"><RotateCcw class="mr-2 size-4" />重置当前编辑</Button><Button :disabled="loading || mutationBusy" @click="saveSettings"><Save class="mr-2 size-4" />保存设置</Button></section>
    </div>
  </section>
</template>
