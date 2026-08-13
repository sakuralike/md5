<script setup lang="ts">
import { createClientId } from "@/lib/clientId";
import {
  ApiError,
  type EmailDeliverySettings,
  type OperationalSettingsSnapshot,
  type SettingChangeReasonCode,
  type SettingVersionDetail,
  type SettingVersionSummary,
  type SettingVersionStatus,
  type SiteNavigationItem,
  type UserLevelDefinition,
} from "@password-detective/api-contract";
import {
  ArrowDownUp,
  BadgeCheck,
  CheckCircle2,
  FileClock,
  Globe2,
  History,
  ImageUp,
  KeyRound,
  MailCheck,
  Navigation,
  Plus,
  RefreshCw,
  Rocket,
  RotateCcw,
  Save,
  Send,
  Server,
  Settings2,
  ShieldCheck,
  Trash2,
} from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  createSettingVersion,
  getEmailDeliverySettings,
  getSettingVersion,
  listSettingVersions,
  publishSettingVersion,
  rollbackSettingVersion,
  sendEmailDeliveryTest,
  uploadSiteLogo,
} from "../services/settings";
import { reauthenticateAdmin } from "../services/users";
import { useAdminAuthStore } from "../stores/auth";

const defaultUserLevels: UserLevelDefinition[] = [
  {
    code: "rookie",
    name: "新手侦探",
    description: "完成注册并开始参与社区协作。",
    min_growth_points: 0,
    daily_reveal_quota: 20,
    can_submit: true,
  },
  {
    code: "apprentice",
    name: "见习侦探",
    description: "持续贡献有效档案或验证反馈。",
    min_growth_points: 100,
    daily_reveal_quota: 30,
    can_submit: true,
  },
  {
    code: "senior",
    name: "资深侦探",
    description: "具备稳定、长期的有效社区贡献。",
    min_growth_points: 500,
    daily_reveal_quota: 50,
    can_submit: true,
  },
  {
    code: "expert",
    name: "专家侦探",
    description: "在贡献和验证活动中保持高质量表现。",
    min_growth_points: 1500,
    daily_reveal_quota: 75,
    can_submit: true,
  },
  {
    code: "chief",
    name: "首席侦探",
    description: "达到社区成长体系的最高长期贡献等级。",
    min_growth_points: 5000,
    daily_reveal_quota: 100,
    can_submit: true,
  },
];

const defaultNavigation: SiteNavigationItem[] = [
  { label: "首页", path: "/", enabled: true, requires_auth: false },
  { label: "社区", path: "/community", enabled: true, requires_auth: false },
];

const defaultSnapshot: OperationalSettingsSnapshot = {
  site_name: "密码侦探社",
  site_logo_url: "",
  site_navigation: defaultNavigation,
  daily_reveal_quota: 20,
  reauthentication_ttl_minutes: 5,
  privacy_deletion_grace_hours: 72,
  desktop_min_client_version: "1.0.0",
  desktop_update_download_cache_seconds: 3600,
  user_levels: defaultUserLevels,
};

const auth = useAdminAuthStore();
const versions = ref<SettingVersionSummary[]>([]);
const publishedVersionId = ref<string | null>(null);
const selected = ref<SettingVersionDetail | null>(null);
const loading = ref(false);
const detailLoading = ref(false);
const mutationBusy = ref(false);
const error = ref("");
const success = ref("");
const reasonCode = ref<SettingChangeReasonCode>("product_policy");
const currentPassword = ref("");
const totpCode = ref("");
const form = ref<OperationalSettingsSnapshot>(structuredClone(defaultSnapshot));
const emailSettings = ref<EmailDeliverySettings | null>(null);
const emailLoading = ref(false);
const emailTestBusy = ref(false);
const emailRecipient = ref("");
const emailMessage = ref("");
const emailError = ref("");
const logoUploadBusy = ref(false);
const logoUploadError = ref("");
const logoUploadMessage = ref("");

const statusLabels: Record<SettingVersionStatus, string> = {
  draft: "草稿",
  published: "当前生效",
  superseded: "历史版本",
};
const reasonLabels: Record<SettingChangeReasonCode, string> = {
  security_hardening: "安全加固",
  capacity_adjustment: "容量调整",
  product_policy: "产品策略",
  incident_response: "事件响应",
  rollback: "版本回滚",
};
const settingLabels: Record<keyof OperationalSettingsSnapshot, string> = {
  site_name: "前端网站名",
  site_logo_url: "前端 Logo",
  site_navigation: "导航按钮",
  daily_reveal_quota: "每日明文查看配额",
  reauthentication_ttl_minutes: "再认证有效期（分钟）",
  privacy_deletion_grace_hours: "账号删除宽限期（小时）",
  desktop_min_client_version: "桌面端最低版本",
  desktop_update_download_cache_seconds: "升级下载缓存（秒）",
  user_levels: "用户等级规则",
};

const canPublish = computed(() => selected.value?.status === "draft");
const canRollback = computed(
  () => selected.value?.status === "superseded" && Boolean(publishedVersionId.value),
);
const currentVersion = computed(() =>
  versions.value.find((item) => item.id === publishedVersionId.value),
);

function describeError(value: unknown): string {
  if (value instanceof ApiError) return value.body.message;
  return value instanceof Error ? value.message : "配置治理服务暂时不可用";
}

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function shortId(value: string | null): string {
  return value ? value.slice(0, 8) : "初始版本";
}

function resetMessages(): void {
  error.value = "";
  success.value = "";
}

function clearCredentials(): void {
  currentPassword.value = "";
  totpCode.value = "";
}

function useSnapshot(snapshot: OperationalSettingsSnapshot): void {
  form.value = structuredClone(snapshot);
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
    logoUploadMessage.value = "图片已上传并写入当前配置表单，请创建草稿并发布后生效。";
  } catch (value) {
    logoUploadError.value = describeError(value);
  } finally {
    logoUploadBusy.value = false;
  }
}

function addUserLevel(): void {
  let sequence = form.value.user_levels.length + 1;
  let code = `custom_${sequence}`;
  while (form.value.user_levels.some((item) => item.code === code)) {
    sequence += 1;
    code = `custom_${sequence}`;
  }
  const previous = form.value.user_levels.at(-1);
  form.value.user_levels.push({
    code,
    name: `自定义等级 ${sequence}`,
    description: "请填写该等级的成长目标与用户权益。",
    min_growth_points: (previous?.min_growth_points ?? 0) + 100,
    daily_reveal_quota: previous?.daily_reveal_quota ?? form.value.daily_reveal_quota,
    can_submit: true,
  });
}

function removeUserLevel(index: number): void {
  if (form.value.user_levels.length <= 1) return;
  form.value.user_levels.splice(index, 1);
  form.value.user_levels.sort((left, right) => left.min_growth_points - right.min_growth_points);
  form.value.user_levels[0].min_growth_points = 0;
}

function normalizedSnapshot(): OperationalSettingsSnapshot {
  // ref.value 是 Vue Reactive Proxy，不能直接传给 structuredClone；手动构造
  // 纯数据快照，确保创建不可变草稿在旧浏览器和非安全上下文也能正常发起请求。
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
  let sequence = form.value.site_navigation.length + 1;
  let path = `/page-${sequence}`;
  while (form.value.site_navigation.some((item) => item.path === path)) {
    sequence += 1;
    path = `/page-${sequence}`;
  }
  form.value.site_navigation.push({
    label: `导航 ${sequence}`,
    path,
    enabled: true,
    requires_auth: false,
  });
}

function removeNavigationItem(index: number): void {
  if (form.value.site_navigation.length <= 1) return;
  form.value.site_navigation.splice(index, 1);
}

function formatDifferenceValue(
  value: number | string | UserLevelDefinition[] | SiteNavigationItem[] | null,
): string {
  if (value === null) return "未设置";
  if (!Array.isArray(value)) return String(value);
  return value
    .map((item) =>
      "path" in item
        ? `${item.label}(${item.path}${item.enabled ? "" : "，停用"}${item.requires_auth ? "，登录可见" : ""})`
        : `${item.name}(${item.min_growth_points}成长值/${item.daily_reveal_quota}次)`,
    )
    .join("；");
}

async function loadDetail(versionId: string): Promise<void> {
  detailLoading.value = true;
  resetMessages();
  try {
    selected.value = await getSettingVersion(versionId, auth.accessToken);
    useSnapshot(selected.value.snapshot);
  } catch (value) {
    error.value = describeError(value);
  } finally {
    detailLoading.value = false;
  }
}

async function loadVersions(preferredId?: string): Promise<void> {
  loading.value = true;
  resetMessages();
  try {
    const response = await listSettingVersions(auth.accessToken);
    versions.value = response.items;
    publishedVersionId.value = response.published_version_id;
    const targetId = preferredId ?? selected.value?.id ?? response.published_version_id ?? response.items[0]?.id;
    if (targetId) {
      await loadDetail(targetId);
    } else {
      selected.value = null;
      useSnapshot(defaultSnapshot);
    }
  } catch (value) {
    error.value = describeError(value);
  } finally {
    loading.value = false;
  }
}

async function createDraft(): Promise<void> {
  mutationBusy.value = true;
  resetMessages();
  try {
    const response = await createSettingVersion(
      {
        expectedBaseVersionId: publishedVersionId.value,
        reasonCode: reasonCode.value,
        snapshot: normalizedSnapshot(),
      },
      auth.accessToken,
      createClientId(),
    );
    await loadVersions(response.version.id);
    success.value = `不可变草稿 ${shortId(response.version.id)} 已创建，可在差异确认后发布。`;
  } catch (value) {
    error.value = describeError(value);
  } finally {
    mutationBusy.value = false;
  }
}

async function acquireSettingsGrant(): Promise<string> {
  if (!currentPassword.value) {
    throw new Error("发布或回滚前必须输入当前密码");
  }
  if (totpCode.value && !/^\d{6,8}$/.test(totpCode.value)) {
    throw new Error("TOTP 动态码必须为 6 至 8 位数字");
  }
  const response = await reauthenticateAdmin(
    {
      currentPassword: currentPassword.value,
      ...(totpCode.value ? { totpCode: totpCode.value } : {}),
      purpose: "admin_settings_governance",
    },
    auth.accessToken,
  );
  return response.reauth_token;
}

async function publishSelected(): Promise<void> {
  if (!selected.value || !canPublish.value) return;
  mutationBusy.value = true;
  resetMessages();
  try {
    const reauthToken = await acquireSettingsGrant();
    const response = await publishSettingVersion(
      selected.value.id,
      {
        expectedPublishedVersionId: publishedVersionId.value,
        reasonCode: reasonCode.value,
        reauthToken,
      },
      auth.accessToken,
      createClientId(),
    );
    await loadVersions(response.version.id);
    success.value = `版本 ${shortId(response.version.id)} 已发布并写入运行时配置投影。`;
  } catch (value) {
    error.value = describeError(value);
  } finally {
    clearCredentials();
    mutationBusy.value = false;
  }
}

async function rollbackSelected(): Promise<void> {
  if (!selected.value || !canRollback.value || !publishedVersionId.value) return;
  mutationBusy.value = true;
  resetMessages();
  try {
    const reauthToken = await acquireSettingsGrant();
    const historicalVersionId = selected.value.id;
    const response = await rollbackSettingVersion(
      historicalVersionId,
      {
        expectedPublishedVersionId: publishedVersionId.value,
        reasonCode: "rollback",
        reauthToken,
      },
      auth.accessToken,
      createClientId(),
    );
    await loadVersions(response.version.id);
    success.value = `已从历史版本 ${shortId(historicalVersionId)} 创建新的不可变回滚版本。`;
  } catch (value) {
    error.value = describeError(value);
  } finally {
    clearCredentials();
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

async function sendTestEmail(): Promise<void> {
  if (!emailRecipient.value.trim()) {
    emailError.value = "请输入用于接收测试邮件的邮箱地址";
    return;
  }
  emailTestBusy.value = true;
  emailError.value = "";
  emailMessage.value = "";
  try {
    const response = await sendEmailDeliveryTest(emailRecipient.value.trim(), auth.accessToken);
    emailMessage.value = `${response.message}，Message-ID：${response.provider_message_id}`;
  } catch (value) {
    emailError.value = describeError(value);
  } finally {
    emailTestBusy.value = false;
  }
}

function refreshPage(): void {
  void loadVersions();
  void loadEmailSettings();
}

onMounted(() => {
  refreshPage();
});
</script>

<template>
  <section class="space-y-6">
    <header class="glass-panel overflow-hidden p-6 sm:p-8">
      <div class="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div class="max-w-3xl space-y-3">
          <div class="flex items-center gap-2 text-sm font-medium text-sky-700">
            <Settings2 class="size-4" />
            N2 · 高风险配置治理
          </div>
          <h1 class="text-3xl font-semibold tracking-tight text-slate-950">系统配置治理工作台</h1>
          <p class="text-sm leading-6 text-slate-600">
            通过不可变版本完成草稿、差异预览、发布与回滚；已启用 TOTP 的管理员需完成动态验证，所有发布操作均要求一次性再认证，并记录最小披露审计事件。
          </p>
        </div>
        <Button variant="outline" :disabled="loading || emailLoading" @click="refreshPage">
          <RefreshCw class="mr-2 size-4" :class="{ 'animate-spin': loading || emailLoading }" />刷新版本
        </Button>
      </div>
    </header>

    <div v-if="error" class="rounded-2xl border border-rose-200 bg-rose-50/90 px-4 py-3 text-sm text-rose-700">
      {{ error }}
    </div>
    <div v-if="success" class="rounded-2xl border border-emerald-200 bg-emerald-50/90 px-4 py-3 text-sm text-emerald-700">
      {{ success }}
    </div>

    <div class="min-w-0 space-y-6">
        <section id="site-appearance" class="glass-panel scroll-mt-28 overflow-hidden p-6 sm:p-8" aria-labelledby="site-appearance-title">
          <div class="flex flex-col gap-4 border-b border-border/70 pb-5 lg:flex-row lg:items-start lg:justify-between">
            <div class="max-w-3xl">
              <div class="flex items-center gap-2 text-sm font-medium text-primary"><Globe2 class="size-4" />前端展示</div>
              <h2 id="site-appearance-title" class="mt-2 text-2xl font-semibold tracking-tight text-foreground">站点外观与导航</h2>
              <p class="mt-2 text-sm leading-6 text-muted-foreground">设置 Web 前端 Logo、网站名和导航栏按钮。仅允许站内路径，避免主导航成为不受控外链入口。</p>
            </div>
            <Badge variant="outline">随配置版本发布</Badge>
          </div>

          <div class="mt-6 grid gap-5 lg:grid-cols-[minmax(0,1fr)_260px]">
            <div class="space-y-5">
              <div class="grid gap-5 sm:grid-cols-2">
                <div class="space-y-2"><Label for="site-name">网站名</Label><Input id="site-name" v-model="form.site_name" maxlength="32" placeholder="密码侦探社" /><p class="text-xs text-muted-foreground">用于导航栏品牌、浏览器标题与页脚。</p></div>
                <div class="space-y-2"><Label for="site-logo-url">Logo 地址</Label><Input id="site-logo-url" v-model="form.site_logo_url" maxlength="500" placeholder="/api/v1/site/assets/logo/… 或 https://…" /><p class="text-xs text-muted-foreground">可直接填写站内路径或 HTTP(S) 图片地址；留空使用默认图标。</p></div>
                <div class="space-y-2 sm:col-span-2">
                  <Label for="site-logo-file">上传 Logo 图片</Label>
                  <div class="flex flex-col gap-3 sm:flex-row sm:items-center">
                    <Input id="site-logo-file" type="file" accept="image/png,image/jpeg,image/webp" :disabled="logoUploadBusy" class="sm:max-w-md" @change="handleLogoUpload" />
                    <Badge variant="outline" class="w-fit"><ImageUp class="mr-1 size-3.5" />PNG / JPEG / WebP · 最大 2 MB</Badge>
                  </div>
                  <p class="text-xs leading-5 text-muted-foreground">文件按内容哈希持久化并生成站内地址；上传完成后仍需创建草稿并发布配置。</p>
                  <p v-if="logoUploadBusy" class="text-xs text-primary">正在上传并校验图片…</p>
                  <p v-if="logoUploadMessage" class="text-xs text-emerald-700">{{ logoUploadMessage }}</p>
                  <p v-if="logoUploadError" class="text-xs text-destructive">{{ logoUploadError }}</p>
                </div>
              </div>
              <div class="space-y-3">
                <div class="flex flex-wrap items-center justify-between gap-3">
                  <div><h3 class="flex items-center gap-2 font-semibold text-foreground"><Navigation class="size-4 text-primary" />导航按钮</h3><p class="mt-1 text-xs text-muted-foreground">最多 8 项，可控制启用状态以及是否仅登录用户可见。</p></div>
                  <Button type="button" variant="outline" size="sm" :disabled="form.site_navigation.length >= 8" @click="addNavigationItem"><Plus class="mr-2 size-4" />新增导航</Button>
                </div>
                <div class="space-y-3">
                  <div v-for="(item, index) in form.site_navigation" :key="`${index}-${item.path}`" class="grid gap-3 rounded-2xl border border-border/70 bg-muted/25 p-4 md:grid-cols-[1fr_1.3fr_auto] md:items-end">
                    <div class="space-y-2"><Label :for="`nav-label-${index}`">按钮名称</Label><Input :id="`nav-label-${index}`" v-model="item.label" maxlength="20" /></div>
                    <div class="space-y-2"><Label :for="`nav-path-${index}`">站内路径</Label><Input :id="`nav-path-${index}`" v-model="item.path" maxlength="120" placeholder="/community" /></div>
                    <Button type="button" variant="ghost" size="icon" :disabled="form.site_navigation.length <= 1" :aria-label="`删除导航 ${item.label}`" @click="removeNavigationItem(index)"><Trash2 class="size-4 text-destructive" /></Button>
                    <div class="flex flex-wrap gap-5 md:col-span-3">
                      <label class="flex items-center gap-2 text-sm text-foreground"><Checkbox v-model:checked="item.enabled" />启用</label>
                      <label class="flex items-center gap-2 text-sm text-foreground"><Checkbox v-model:checked="item.requires_auth" />仅登录用户可见</label>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div class="rounded-2xl border border-border/70 bg-muted/25 p-5">
              <p class="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">实时预览</p>
              <div class="mt-4 flex items-center gap-3 rounded-2xl border border-border bg-card p-4 shadow-sm">
                <img v-if="form.site_logo_url" :src="form.site_logo_url" alt="Logo 预览" class="size-12 rounded-xl object-contain" />
                <div v-else class="grid size-12 place-items-center rounded-xl bg-primary text-lg font-semibold text-primary-foreground">密</div>
                <div class="min-w-0"><p class="truncate font-semibold text-foreground">{{ form.site_name || "未命名站点" }}</p><p class="text-xs text-muted-foreground">Web 品牌预览</p></div>
              </div>
              <div class="mt-4 flex flex-wrap gap-2"><Badge v-for="item in form.site_navigation.filter((entry) => entry.enabled)" :key="item.path" variant="secondary">{{ item.label }}</Badge></div>
            </div>
          </div>
        </section>

        <section id="email-delivery" class="glass-panel scroll-mt-28 overflow-hidden p-6 sm:p-8" aria-labelledby="email-delivery-title">
      <div class="flex flex-col gap-4 border-b border-border/70 pb-5 lg:flex-row lg:items-start lg:justify-between">
        <div class="max-w-3xl">
          <div class="flex items-center gap-2 text-sm font-medium text-primary">
            <MailCheck class="size-4" />邮件功能
          </div>
          <h2 id="email-delivery-title" class="mt-2 text-2xl font-semibold tracking-tight text-foreground">SMTP 邮件投递</h2>
          <p class="mt-2 text-sm leading-6 text-muted-foreground">
            参考邮件控制台布局展示发件人、邮件内容和 SMTP 连接参数。生产密码继续由 Docker Secrets 注入，页面不会读取或回显明文凭据。
          </p>
        </div>
        <Badge :variant="emailSettings?.enabled ? 'default' : 'outline'">
          {{ emailSettings?.enabled ? "SMTP 已启用" : "SMTP 未启用" }}
        </Badge>
      </div>

      <div v-if="emailError" class="mt-5 rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
        {{ emailError }}
      </div>
      <div v-if="emailMessage" class="mt-5 rounded-xl border border-emerald-200 bg-emerald-50/90 px-4 py-3 text-sm text-emerald-700">
        {{ emailMessage }}
      </div>

      <div v-if="emailLoading && !emailSettings" class="py-10 text-center text-sm text-muted-foreground">正在读取邮件配置…</div>
      <div v-else-if="emailSettings" class="mt-6 space-y-7">
        <div class="grid gap-5 lg:grid-cols-2">
          <div class="space-y-2">
            <Label for="email-sender-name">自定义发件人</Label>
            <Input id="email-sender-name" :model-value="emailSettings.sender_name || '未配置'" readonly />
            <p class="text-xs leading-5 text-muted-foreground">收件人看到的发件人昵称，由部署配置提供。</p>
          </div>
          <div class="space-y-2">
            <Label for="email-sender-address">发件邮箱账号</Label>
            <Input id="email-sender-address" :model-value="emailSettings.sender_email || '未配置'" readonly />
            <p class="text-xs leading-5 text-muted-foreground">必须与邮件服务商允许的发件地址一致。</p>
          </div>
          <div class="space-y-2">
            <Label for="email-subject-prefix">自定义标题前缀</Label>
            <Input id="email-subject-prefix" :model-value="emailSettings.subject_prefix" readonly />
            <p class="text-xs leading-5 text-muted-foreground">系统验证、重置、案件和风险告警邮件统一使用该前缀。</p>
          </div>
          <div class="space-y-2">
            <Label for="email-content-format">邮件内容格式</Label>
            <Input id="email-content-format" model-value="UTF-8 纯文本" readonly />
            <p class="text-xs leading-5 text-muted-foreground">不发送远程图片、追踪像素、附件或不受控 HTML。</p>
          </div>
          <div class="space-y-2 lg:col-span-2">
            <Label for="email-footer">邮件底部额外内容</Label>
            <Textarea id="email-footer" :model-value="emailSettings.footer_text" readonly rows="3" />
            <p class="text-xs leading-5 text-muted-foreground">安全邮件不提供可注入的 HTML 链接；业务入口统一引导用户登录网站或管理端处理。</p>
          </div>
        </div>

        <div class="rounded-2xl border border-border/70 bg-muted/30 p-5">
          <div class="mb-5 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 class="flex items-center gap-2 font-semibold text-foreground"><Server class="size-4 text-primary" />SMTP 服务器</h3>
              <p class="mt-1 text-sm text-muted-foreground">连接参数仅展示非秘密字段，密码只显示是否已经配置。</p>
            </div>
            <Badge variant="outline">{{ emailSettings.configuration_source === "deployment_environment" ? "部署环境 / Docker Secrets" : emailSettings.configuration_source }}</Badge>
          </div>
          <div class="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
            <div class="space-y-2"><Label for="smtp-host">邮件服务器地址</Label><Input id="smtp-host" :model-value="emailSettings.smtp_host || '未配置'" readonly /></div>
            <div class="space-y-2"><Label for="smtp-port">SMTP 服务器端口</Label><Input id="smtp-port" :model-value="String(emailSettings.smtp_port)" readonly /></div>
            <div class="space-y-2"><Label for="smtp-security">加密方式</Label><Input id="smtp-security" :model-value="emailSettings.smtp_security.toUpperCase()" readonly /></div>
            <div class="space-y-2"><Label for="smtp-user">SMTP 用户名</Label><Input id="smtp-user" :model-value="emailSettings.smtp_username || '未配置'" readonly /></div>
            <div class="space-y-2"><Label for="smtp-auth">SMTPAuth 服务</Label><Input id="smtp-auth" :model-value="emailSettings.smtp_auth_enabled ? '已启用' : '未启用'" readonly /></div>
            <div class="space-y-2"><Label for="smtp-password"><KeyRound class="mr-1 inline size-4" />SMTP 服务邮箱密码</Label><Input id="smtp-password" :model-value="emailSettings.smtp_password_configured ? '••••••••（已通过 Secret 配置）' : '未配置'" readonly /></div>
          </div>
        </div>

        <div class="rounded-2xl border border-amber-200 bg-amber-50/75 p-5">
          <div class="grid gap-4 lg:grid-cols-[1fr_auto] lg:items-end">
            <div class="space-y-2">
              <Label for="smtp-test-recipient">测试收件邮箱</Label>
              <Input id="smtp-test-recipient" v-model="emailRecipient" type="email" autocomplete="email" placeholder="operator@example.com" />
              <p class="text-xs leading-5 text-amber-800">测试邮件只验证 SMTP 会话已被服务器接受，不等同于最终送达、打开或点击回执。</p>
            </div>
            <Button :disabled="emailTestBusy || !emailSettings.smtp_configured" @click="sendTestEmail">
              <Send class="mr-2 size-4" />{{ emailTestBusy ? "发送中…" : "发送测试邮件" }}
            </Button>
          </div>
        </div>
      </div>
    </section>

    <div class="min-w-0 space-y-6" data-layout="stacked-settings-regions">
      <div class="min-w-0 space-y-6">
        <section id="version-history" class="glass-panel scroll-mt-28 p-6">
          <div class="mb-5 flex items-start justify-between gap-4">
            <div>
              <h2 class="flex items-center gap-2 text-lg font-semibold text-slate-950">
                <History class="size-5 text-sky-600" />不可变版本历史
              </h2>
              <p class="mt-1 text-sm text-slate-500">当前生效：{{ shortId(publishedVersionId) }} · 共 {{ versions.length }} 个版本</p>
            </div>
            <Badge variant="outline">schema operational-v1</Badge>
          </div>

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>版本</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>原因</TableHead>
                <TableHead>时间</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableEmpty v-if="!loading && versions.length === 0" :colspan="4">尚无配置版本，请创建首个草稿。</TableEmpty>
              <TableRow
                v-for="item in versions"
                :key="item.id"
                class="cursor-pointer"
                :class="{ 'bg-sky-50/70': selected?.id === item.id }"
                @click="loadDetail(item.id)"
              >
                <TableCell class="font-mono text-xs">{{ shortId(item.id) }}</TableCell>
                <TableCell><Badge variant="outline">{{ statusLabels[item.status] }}</Badge></TableCell>
                <TableCell>{{ reasonLabels[item.reason_code as SettingChangeReasonCode] ?? item.reason_code }}</TableCell>
                <TableCell class="text-xs text-slate-500">{{ formatDate(item.published_at ?? item.created_at) }}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </section>

        <section id="operational-policy" class="glass-panel scroll-mt-28 p-6">
          <div class="mb-5">
            <h2 class="flex items-center gap-2 text-lg font-semibold text-slate-950">
              <Save class="size-5 text-sky-600" />配置草稿编辑器
            </h2>
            <p class="mt-1 text-sm text-slate-500">以当前生效版本为基线创建新草稿，不会直接覆盖运行时配置。</p>
          </div>

          <div class="grid gap-4 sm:grid-cols-2">
            <div class="space-y-2">
              <Label for="daily-quota">每日明文查看配额</Label>
              <Input id="daily-quota" v-model.number="form.daily_reveal_quota" type="number" min="1" max="1000" />
            </div>
            <div class="space-y-2">
              <Label for="reauth-ttl">再认证有效期（分钟）</Label>
              <Input id="reauth-ttl" v-model.number="form.reauthentication_ttl_minutes" type="number" min="1" max="15" />
            </div>
            <div class="space-y-2">
              <Label for="deletion-grace">账号删除宽限期（小时）</Label>
              <Input id="deletion-grace" v-model.number="form.privacy_deletion_grace_hours" type="number" min="1" max="720" />
            </div>
            <div class="space-y-2">
              <Label for="min-client">桌面端最低版本</Label>
              <Input id="min-client" v-model="form.desktop_min_client_version" placeholder="1.0.0" />
            </div>
            <div class="space-y-2">
              <Label for="download-cache">升级下载缓存（秒）</Label>
              <Input id="download-cache" v-model.number="form.desktop_update_download_cache_seconds" type="number" min="60" max="31536000" />
            </div>
            <div class="space-y-2">
              <Label>变更原因码</Label>
              <Select v-model="reasonCode">
                <SelectTrigger aria-label="配置变更原因码"><SelectValue placeholder="选择原因" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="security_hardening">安全加固</SelectItem>
                  <SelectItem value="capacity_adjustment">容量调整</SelectItem>
                  <SelectItem value="product_policy">产品策略</SelectItem>
                  <SelectItem value="incident_response">事件响应</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

        </section>

        <section id="user-levels" class="glass-panel scroll-mt-28 p-6">
          <div class="mb-5 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 class="flex items-center gap-2 text-lg font-semibold text-slate-950"><BadgeCheck class="size-5 text-sky-600" />用户等级与权益</h2>
              <p class="mt-1 text-sm text-slate-500">成长值门槛必须唯一并按升序排列；首级门槛固定为 0。发布后会重建全部用户等级投影。</p>
            </div>
            <Button type="button" variant="outline" size="sm" @click="addUserLevel"><Plus class="mr-2 size-4" />新增等级</Button>
          </div>

            <div class="flex snap-x gap-4 overflow-x-auto pb-3" aria-label="用户等级横向列表" tabindex="0">
              <article
                v-for="(level, index) in form.user_levels"
                :key="`${level.code}-${index}`"
                class="w-80 shrink-0 snap-start rounded-xl border border-border/80 bg-background/70 p-4 sm:w-96"
              >
              <div class="mb-4 flex items-center justify-between gap-3">
                <div class="flex items-center gap-2">
                  <Badge variant="outline">第 {{ index + 1 }} 级</Badge>
                  <span class="text-sm font-medium text-foreground">{{ level.name }}</span>
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  :disabled="form.user_levels.length <= 1"
                  :aria-label="`删除等级 ${level.name}`"
                  @click="removeUserLevel(index)"
                >
                  <Trash2 class="size-4 text-destructive" />
                </Button>
              </div>
                <div class="grid grid-cols-2 gap-4">
                <div class="space-y-2">
                  <Label :for="`level-code-${index}`">等级代码</Label>
                  <Input :id="`level-code-${index}`" v-model="level.code" placeholder="senior" />
                </div>
                <div class="space-y-2">
                  <Label :for="`level-name-${index}`">等级名称</Label>
                  <Input :id="`level-name-${index}`" v-model="level.name" placeholder="资深侦探" />
                </div>
                <div class="space-y-2">
                  <Label :for="`level-threshold-${index}`">成长值门槛</Label>
                  <Input
                    :id="`level-threshold-${index}`"
                    v-model.number="level.min_growth_points"
                    type="number"
                    min="0"
                    :disabled="index === 0"
                  />
                </div>
                <div class="space-y-2">
                  <Label :for="`level-quota-${index}`">每日揭示配额</Label>
                  <Input
                    :id="`level-quota-${index}`"
                    v-model.number="level.daily_reveal_quota"
                    type="number"
                    min="1"
                    max="1000"
                  />
                </div>
                  <div class="col-span-2 space-y-2">
                  <Label :for="`level-description-${index}`">等级说明</Label>
                  <Input
                    :id="`level-description-${index}`"
                    v-model="level.description"
                    placeholder="说明该等级的成长目标与权益"
                  />
                </div>
                <div class="flex items-center gap-2">
                  <Checkbox :id="`level-submit-${index}`" v-model="level.can_submit" />
                  <Label :for="`level-submit-${index}`">允许提交档案</Label>
                </div>
              </div>
              </article>
            </div>

          <Button type="button" class="mt-5" :disabled="mutationBusy" @click="createDraft">
            <Save class="mr-2 size-4" />创建不可变草稿
          </Button>
        </section>
      </div>

      <div class="space-y-6">
        <section class="glass-panel p-6">
          <div class="mb-5 flex items-start justify-between gap-4">
            <div>
              <h2 class="flex items-center gap-2 text-lg font-semibold text-slate-950">
                <ArrowDownUp class="size-5 text-sky-600" />版本差异预览
              </h2>
              <p class="mt-1 text-sm text-slate-500">{{ selected ? `版本 ${shortId(selected.id)}` : "请选择一个版本" }}</p>
            </div>
            <Badge v-if="selected" variant="outline">{{ statusLabels[selected.status] }}</Badge>
          </div>

          <div v-if="detailLoading" class="py-10 text-center text-sm text-slate-500">正在加载版本详情…</div>
          <div v-else-if="selected" class="space-y-3">
            <div
              v-for="difference in selected.differences"
              :key="difference.key"
              class="rounded-xl border border-white/70 bg-white/65 p-4"
            >
              <p class="text-sm font-medium text-slate-800">{{ settingLabels[difference.key] }}</p>
              <div class="mt-2 grid grid-cols-[1fr_auto_1fr] items-center gap-3 text-sm">
                <code class="rounded bg-muted px-2 py-1 text-muted-foreground">{{ formatDifferenceValue(difference.previous) }}</code>
                <span class="text-slate-400">→</span>
                <code class="rounded bg-sky-50 px-2 py-1 text-sky-700">{{ formatDifferenceValue(difference.current) }}</code>
              </div>
            </div>
            <div v-if="selected.differences.length === 0" class="rounded-xl border border-emerald-200 bg-emerald-50/70 p-4 text-sm text-emerald-700">
              <CheckCircle2 class="mr-2 inline size-4" />该版本与基线没有字段差异。
            </div>
            <dl class="grid grid-cols-2 gap-3 border-t border-slate-200/70 pt-4 text-xs text-slate-500">
              <div><dt>快照哈希</dt><dd class="mt-1 font-mono">{{ selected.snapshot_hash.slice(0, 16) }}…</dd></div>
              <div><dt>生效时间</dt><dd class="mt-1">{{ formatDate(selected.effective_at) }}</dd></div>
              <div><dt>基线版本</dt><dd class="mt-1 font-mono">{{ shortId(selected.base_version_id) }}</dd></div>
              <div><dt>回滚来源</dt><dd class="mt-1 font-mono">{{ shortId(selected.rollback_of_id) }}</dd></div>
            </dl>
          </div>
          <div v-else class="py-10 text-center text-sm text-slate-500">暂无可预览版本。</div>
        </section>

        <section id="publish-gate" class="glass-panel scroll-mt-28 p-6">
          <div class="mb-5">
            <h2 class="flex items-center gap-2 text-lg font-semibold text-slate-950">
              <ShieldCheck class="size-5 text-sky-600" />发布与回滚门禁
            </h2>
            <p class="mt-1 text-sm text-slate-500">一次性再认证令牌仅用于当前配置操作，成功或失败后立即清空凭据。</p>
          </div>
          <div class="grid gap-4 sm:grid-cols-2">
            <div class="space-y-2">
              <Label for="settings-password">当前密码</Label>
              <Input id="settings-password" v-model="currentPassword" type="password" autocomplete="current-password" />
            </div>
            <div class="space-y-2">
              <Label for="settings-totp">TOTP 动态码（已启用时填写）</Label>
              <Input id="settings-totp" v-model="totpCode" inputmode="numeric" maxlength="6" autocomplete="one-time-code" />
            </div>
          </div>
          <div class="mt-5 flex flex-wrap gap-3">
            <Button :disabled="mutationBusy || !canPublish" @click="publishSelected">
              <Rocket class="mr-2 size-4" />发布选中草稿
            </Button>
            <Button variant="destructive" :disabled="mutationBusy || !canRollback" @click="rollbackSelected">
              <RotateCcw class="mr-2 size-4" />回滚到选中历史版本
            </Button>
          </div>
          <div class="mt-4 rounded-xl border border-amber-200 bg-amber-50/75 p-3 text-xs leading-5 text-amber-800">
            <FileClock class="mr-1 inline size-4" />
            发布使用乐观并发校验。若当前生效版本已变化，服务端会拒绝操作且不会消耗一次性再认证授权。
          </div>
        </section>

        <section class="glass-panel p-5 text-sm text-slate-600">
          <div class="flex items-center gap-2 font-medium text-slate-900"><CheckCircle2 class="size-4 text-emerald-600" />运行时投影</div>
          <p class="mt-2 leading-6">
            当前版本 {{ shortId(currentVersion?.id ?? null) }} 发布后会原子更新系统配置投影，历史快照保持不可变，回滚也会创建一个新版本而不是改写旧记录。
          </p>
        </section>
      </div>
    </div>
    </div>
  </section>
</template>
