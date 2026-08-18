<script setup lang="ts">
import { createClientId } from "@/lib/clientId";
import { cloneOperationalSettingsSnapshot } from "@/lib/operationalSettingsForm";
import {
  cloneEmailDeliveryForm,
  emailFormFromSettings,
} from "@/lib/emailDeliveryForm";
import {
  cloneSeoSettingsForm,
  createSeoSettingsForm,
  seoSettingsPayload,
  type SeoSettingsForm,
} from "@/lib/seoSettingsForm";
import {
  ApiError,
  type EmailDeliverySettings,
  type EmailDeliverySettingsUpdate,
  type OperationalSettingsSnapshot,
  type SeoSettings,
  type SeoSettingsResponse,
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
  Search,
  Send,
  Server,
  Settings2,
  Trash2,
} from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";
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
  getCurrentSettings,
  getEmailDeliverySettings,
  getSeoSettings,
  saveCurrentSettings,
  saveEmailDeliverySettings,
  saveSeoSettings as persistSeoSettings,
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

const defaultSeoSettings: SeoSettings = {
  enabled: false,
  indexing_enabled: false,
  home_title: "密码侦探社",
  keywords: [],
  description: "",
  title_separator: "-",
  default_image_url: "",
  open_graph_enabled: false,
  sitemap_enabled: false,
};

const auth = useAdminAuthStore();
const form = ref<OperationalSettingsSnapshot>(cloneOperationalSettingsSnapshot(defaultSnapshot));
const baselineSnapshot = ref<OperationalSettingsSnapshot>(cloneOperationalSettingsSnapshot(defaultSnapshot));
const loading = ref(false);
const mutationBusy = ref(false);
const error = ref("");
const success = ref("");
const emailSettings = ref<EmailDeliverySettings | null>(null);
const emailForm = ref<EmailDeliverySettingsUpdate | null>(null);
const emailBaseline = ref<EmailDeliverySettingsUpdate | null>(null);
const emailSaveBusy = ref(false);
const emailLoading = ref(false);
const emailTestBusy = ref(false);
const emailRecipient = ref("");
const emailMessage = ref("");
const emailError = ref("");
const logoUploadBusy = ref(false);
const logoUploadError = ref("");
const logoUploadMessage = ref("");
const seoSettings = ref<SeoSettingsResponse | null>(null);
const seoForm = ref<SeoSettingsForm>(createSeoSettingsForm(defaultSeoSettings));
const seoBaseline = ref<SeoSettingsForm>(createSeoSettingsForm(defaultSeoSettings));
const seoLoading = ref(false);
const seoSaveBusy = ref(false);
const seoError = ref("");
const seoMessage = ref("");
const seoPreviewTitle = computed(() => {
  const siteName = form.value.site_name.trim() || "密码侦探社";
  const homeTitle = seoForm.value.home_title.trim() || siteName;
  return homeTitle === siteName
    ? siteName
    : `${homeTitle} ${seoForm.value.title_separator} ${siteName}`;
});
const seoPreviewKeywords = computed(
  () => seoSettingsPayload(seoForm.value).keywords.join("、") || "未设置关键词",
);

function describeError(value: unknown): string {
  return value instanceof ApiError ? value.message : "请求失败，请稍后重试";
}

function resetEmailEdits(): void {
  if (emailBaseline.value) emailForm.value = cloneEmailDeliveryForm(emailBaseline.value);
  emailError.value = "";
  emailMessage.value = "已恢复到当前已保存的 SMTP 设置。";
}

function resetMessages(): void {
  error.value = "";
  success.value = "";
}

function resetSeoEdits(): void {
  seoForm.value = cloneSeoSettingsForm(seoBaseline.value);
  seoError.value = "";
  seoMessage.value = "已恢复到当前已保存的 SEO 设置。";
}

function useSnapshot(snapshot: OperationalSettingsSnapshot): void {
  const persisted = cloneOperationalSettingsSnapshot(snapshot);
  baselineSnapshot.value = persisted;
  form.value = cloneOperationalSettingsSnapshot(persisted);
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

async function loadSeoSettings(): Promise<void> {
  seoLoading.value = true;
  seoError.value = "";
  try {
    const response = await getSeoSettings(auth.accessToken);
    seoSettings.value = response;
    seoBaseline.value = createSeoSettingsForm(response.settings);
    seoForm.value = cloneSeoSettingsForm(seoBaseline.value);
  } catch (value) {
    seoError.value = describeError(value);
  } finally {
    seoLoading.value = false;
  }
}

async function saveSeoSettings(): Promise<void> {
  seoError.value = "";
  seoMessage.value = "";
  seoSaveBusy.value = true;
  try {
    const response = await persistSeoSettings(
      seoSettingsPayload(seoForm.value),
      auth.accessToken,
      createClientId(),
    );
    seoSettings.value = response;
    seoBaseline.value = createSeoSettingsForm(response.settings);
    seoForm.value = cloneSeoSettingsForm(seoBaseline.value);
    seoMessage.value = "SEO 设置已直接保存并立即生效。";
  } catch (value) {
    seoError.value = describeError(value);
  } finally {
    seoSaveBusy.value = false;
  }
}

async function loadEmailSettings(): Promise<void> {
  emailLoading.value = true;
  emailError.value = "";
  try {
    const settings = await getEmailDeliverySettings(auth.accessToken);
    emailSettings.value = settings;
    const baseline = emailFormFromSettings(settings);
    emailBaseline.value = baseline;
    emailForm.value = cloneEmailDeliveryForm(baseline);
  } catch (value) {
    emailError.value = describeError(value);
  } finally {
    emailLoading.value = false;
  }
}

async function saveEmailSettings(): Promise<void> {
  if (!emailForm.value) return;
  emailError.value = "";
  emailMessage.value = "";
  emailSaveBusy.value = true;
  try {
    const payload: EmailDeliverySettingsUpdate = {
      ...emailForm.value,
      sender_name: emailForm.value.sender_name.trim(),
      sender_email: emailForm.value.sender_email.trim(),
      subject_prefix: emailForm.value.subject_prefix.trim(),
      footer_text: emailForm.value.footer_text.trim(),
      footer_html: emailForm.value.footer_html.trim(),
      smtp_host: emailForm.value.smtp_host.trim(),
      smtp_username: emailForm.value.smtp_username.trim(),
      smtp_port: Number(emailForm.value.smtp_port),
      smtp_timeout_seconds: Number(emailForm.value.smtp_timeout_seconds),
      smtp_password: emailForm.value.smtp_password?.trim() || null,
    };
    const saved = await saveEmailDeliverySettings(payload, auth.accessToken, createClientId());
    emailSettings.value = saved;
    const baseline = emailFormFromSettings(saved);
    emailBaseline.value = baseline;
    emailForm.value = cloneEmailDeliveryForm(baseline);
    emailMessage.value = "SMTP 邮件投递设置已直接保存并立即生效。";
  } catch (value) {
    emailError.value = describeError(value);
  } finally {
    emailSaveBusy.value = false;
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
    await loadSeoSettings();
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

      <section id="seo-settings" class="glass-panel scroll-mt-28 p-6" data-section="seo-settings">
        <div class="mb-5 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 class="flex items-center gap-2 text-lg font-semibold text-foreground"><Search class="size-5 text-primary" />SEO 设置</h2>
            <p class="mt-1 text-sm leading-6 text-muted-foreground">参考 Zibll 主题的邮件与 SEO 设置方式，保存后当前配置立即生效；不创建版本、发布或回滚快照。</p>
          </div>
          <span class="rounded-full border border-border bg-background px-3 py-1 text-xs font-medium text-muted-foreground">直接保存</span>
        </div>

        <div v-if="seoLoading" class="rounded-xl border border-border bg-background px-4 py-3 text-sm text-muted-foreground">正在加载 SEO 设置…</div>
        <div v-else class="space-y-5">
          <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Label class="flex min-h-12 items-center gap-3 rounded-xl border border-border bg-background px-3 py-2 text-sm"><Checkbox id="seo-enabled" :model-value="seoForm.enabled" @update:model-value="seoForm.enabled = $event === true" /><span><span class="block font-medium text-foreground">启用 SEO</span><span class="block text-xs text-muted-foreground">输出站点 SEO 公共配置。</span></span></Label>
            <Label class="flex min-h-12 items-center gap-3 rounded-xl border border-border bg-background px-3 py-2 text-sm"><Checkbox id="seo-indexing-enabled" :model-value="seoForm.indexing_enabled" @update:model-value="seoForm.indexing_enabled = $event === true" /><span><span class="block font-medium text-foreground">允许搜索引擎收录</span><span class="block text-xs text-muted-foreground">关闭时 robots 全站禁止抓取。</span></span></Label>
            <Label class="flex min-h-12 items-center gap-3 rounded-xl border border-border bg-background px-3 py-2 text-sm"><Checkbox id="seo-sitemap-enabled" :model-value="seoForm.sitemap_enabled" @update:model-value="seoForm.sitemap_enabled = $event === true" /><span><span class="block font-medium text-foreground">启用 Sitemap</span><span class="block text-xs text-muted-foreground">仅输出显式公开路由。</span></span></Label>
            <Label class="flex min-h-12 items-center gap-3 rounded-xl border border-border bg-background px-3 py-2 text-sm"><Checkbox id="seo-open-graph-enabled" :model-value="seoForm.open_graph_enabled" @update:model-value="seoForm.open_graph_enabled = $event === true" /><span><span class="block font-medium text-foreground">启用 Open Graph</span><span class="block text-xs text-muted-foreground">为公开页面提供社交分享信息。</span></span></Label>
          </div>

          <div class="grid gap-4 lg:grid-cols-2">
            <div class="space-y-2"><Label for="seo-home-title">首页 SEO 标题</Label><Input id="seo-home-title" v-model="seoForm.home_title" maxlength="120" placeholder="密码侦探社" /><p class="text-xs text-muted-foreground">用于首页标题预览和后续 Web 运行时元标签。</p></div>
            <div class="space-y-2"><Label for="seo-keywords">全站关键词</Label><Input id="seo-keywords" v-model="seoForm.keywords_text" maxlength="500" placeholder="密码, 压缩包, 社区" /><p class="text-xs text-muted-foreground">使用逗号或中文逗号分隔，保存时会去空格、去重。</p></div>
            <div class="space-y-2 lg:col-span-2"><Label for="seo-description">全站描述</Label><Textarea id="seo-description" v-model="seoForm.description" rows="4" maxlength="320" placeholder="请输入面向搜索引擎的站点描述。" /><p class="text-xs text-muted-foreground">描述只保存为当前 SEO 配置，不会写入版本历史或额外预览对象。</p></div>
            <div class="space-y-2"><Label for="seo-title-separator">标题连接符</Label><Select v-model="seoForm.title_separator"><SelectTrigger id="seo-title-separator" aria-label="标题连接符"><SelectValue placeholder="选择连接符" /></SelectTrigger><SelectContent><SelectItem value="-">短横线（-）</SelectItem><SelectItem value="_">下划线（_）</SelectItem><SelectItem value="|">竖线（|）</SelectItem><SelectItem value="·">中点（·）</SelectItem></SelectContent></Select><p class="text-xs text-muted-foreground">仅允许有限连接符，避免把任意 HTML 写入标题。</p></div>
            <div class="space-y-2"><Label for="seo-default-image">默认 SEO/社交图片</Label><Input id="seo-default-image" v-model="seoForm.default_image_url" maxlength="500" placeholder="https://synthetic.example.com/seo.png" /><p class="text-xs text-muted-foreground">仅作为公开页面缺省图片，内容级封面列入后续阶段。</p></div>
          </div>

          <div class="rounded-xl border border-dashed border-border bg-background p-4" data-seo-preview>
            <div class="mb-3 flex items-center justify-between gap-3"><div><h3 class="text-sm font-semibold text-foreground">搜索结果预览</h3><p class="text-xs text-muted-foreground">仅为当前编辑状态的本地预览，不会单独提交。</p></div><span class="text-xs text-muted-foreground">/</span></div>
            <p class="text-lg font-medium text-primary">{{ seoPreviewTitle }}</p>
            <p class="mt-1 line-clamp-2 text-sm text-muted-foreground">{{ seoForm.description.trim() || "保存描述后将在这里显示搜索结果摘要。" }}</p>
            <p class="mt-2 text-xs text-muted-foreground">关键词：{{ seoPreviewKeywords }}</p>
          </div>

          <div class="flex flex-wrap gap-3">
            <Button :disabled="seoSaveBusy || seoLoading" @click="saveSeoSettings"><Save class="mr-2 size-4" />保存 SEO 设置</Button>
            <Button type="button" variant="outline" :disabled="seoSaveBusy || seoLoading" @click="resetSeoEdits"><RotateCcw class="mr-2 size-4" />重置 SEO 编辑</Button>
          </div>
          <p v-if="seoMessage" class="text-sm text-primary">{{ seoMessage }}</p>
          <p v-if="seoError" class="text-sm text-destructive">{{ seoError }}</p>
        </div>
      </section>

      <section id="operational-policy" class="glass-panel scroll-mt-28 p-6">
        <div class="mb-5"><h2 class="flex items-center gap-2 text-lg font-semibold text-foreground"><Server class="size-5 text-primary" />运行参数</h2><p class="mt-1 text-sm text-muted-foreground">这些设置会在保存后直接更新运行时配置。</p></div>
        <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"><div class="space-y-2"><Label for="daily-quota">每日明文查看配额</Label><Input id="daily-quota" v-model.number="form.daily_reveal_quota" type="number" min="1" max="1000" /></div><div class="space-y-2"><Label for="reauth-ttl">再认证有效期（分钟）</Label><Input id="reauth-ttl" v-model.number="form.reauthentication_ttl_minutes" type="number" min="1" max="15" /></div><div class="space-y-2"><Label for="deletion-grace">账号删除宽限期（小时）</Label><Input id="deletion-grace" v-model.number="form.privacy_deletion_grace_hours" type="number" min="1" max="720" /></div><div class="space-y-2"><Label for="min-client">桌面端最低版本</Label><Input id="min-client" v-model="form.desktop_min_client_version" placeholder="1.0.0" /></div><div class="space-y-2"><Label for="download-cache">升级下载缓存（秒）</Label><Input id="download-cache" v-model.number="form.desktop_update_download_cache_seconds" type="number" min="60" max="31536000" /></div></div>
      </section>

      <section id="email-delivery" class="glass-panel scroll-mt-28 p-6">
        <div class="mb-5"><h2 class="flex items-center gap-2 text-lg font-semibold text-foreground"><MailCheck class="size-5 text-primary" />SMTP 邮件投递</h2><p class="mt-1 text-sm text-muted-foreground">参照主题邮件设置管理发件人、标题前缀、邮件底部内容与 SMTP 传输参数。授权码只可写入，不会回显。</p></div>
        <div v-if="emailLoading" class="text-sm text-muted-foreground">正在加载邮件配置…</div>
        <div v-else-if="emailForm" class="space-y-5">
          <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div class="space-y-2"><Label for="smtp-enabled">启用 SMTP 投递</Label><Label class="flex h-10 items-center gap-2"><Checkbox id="smtp-enabled" :model-value="emailForm.enabled" @update:model-value="emailForm.enabled = $event === true" />启用后，邮件通知将使用当前配置投递。</Label></div>
            <div class="space-y-2"><Label for="smtp-sender-name">自定义发件人</Label><Input id="smtp-sender-name" v-model="emailForm.sender_name" /></div>
            <div class="space-y-2"><Label for="smtp-sender-email">发信人邮箱账号</Label><Input id="smtp-sender-email" v-model="emailForm.sender_email" type="email" /></div>
            <div class="space-y-2"><Label for="smtp-subject-prefix">自定义标题前缀</Label><Input id="smtp-subject-prefix" v-model="emailForm.subject_prefix" /></div>
            <div class="space-y-2"><Label for="smtp-host">邮件服务器地址</Label><Input id="smtp-host" v-model="emailForm.smtp_host" placeholder="smtp.example.com" /></div>
            <div class="space-y-2"><Label for="smtp-port">SMTP 服务器端口</Label><Input id="smtp-port" v-model.number="emailForm.smtp_port" type="number" min="1" max="65535" /></div>
            <div class="space-y-2"><Label for="smtp-security">加密方式</Label><Input id="smtp-security" v-model="emailForm.smtp_security" placeholder="starttls、ssl 或 none" /></div>
            <div class="space-y-2"><Label for="smtp-username">SMTP 用户名</Label><Input id="smtp-username" v-model="emailForm.smtp_username" /></div>
            <div class="space-y-2"><Label for="smtp-password">SMTP 授权码</Label><Input id="smtp-password" :model-value="emailForm.smtp_password ?? ''" @update:model-value="emailForm.smtp_password = String($event)" type="password" autocomplete="new-password" placeholder="留空则保留原授权码" /></div>
            <div class="space-y-2"><Label for="smtp-auth">SMTPAuth 服务</Label><Label class="flex h-10 items-center gap-2"><Checkbox id="smtp-auth" :model-value="emailForm.smtp_auth_enabled" @update:model-value="emailForm.smtp_auth_enabled = $event === true" />使用用户名与授权码认证。</Label></div>
            <div class="space-y-2"><Label for="smtp-timeout">连接超时（秒）</Label><Input id="smtp-timeout" v-model.number="emailForm.smtp_timeout_seconds" type="number" min="1" max="60" /></div>
            <div class="space-y-2"><Label for="smtp-clear-password">清除保存的授权码</Label><Label class="flex h-10 items-center gap-2"><Checkbox id="smtp-clear-password" :model-value="emailForm.clear_smtp_password" @update:model-value="emailForm.clear_smtp_password = $event === true" />下一次保存时清除授权码。</Label></div>
          </div>
          <div class="grid gap-4 lg:grid-cols-2">
            <div class="space-y-2"><Label for="smtp-footer-text">邮件底部额外内容</Label><Textarea id="smtp-footer-text" v-model="emailForm.footer_text" rows="4" /></div>
            <div class="space-y-2"><Label for="smtp-footer-html">邮件底部链接（支持基础 HTML）</Label><Textarea id="smtp-footer-html" v-model="emailForm.footer_html" rows="4" placeholder='<a href="https://example.com">访问网站</a>' /></div>
          </div>
          <div class="flex flex-wrap gap-3"><Button :disabled="emailSaveBusy" @click="saveEmailSettings"><Save class="mr-2 size-4" />保存 SMTP 设置</Button><Button type="button" variant="outline" :disabled="emailSaveBusy" @click="resetEmailEdits"><RotateCcw class="mr-2 size-4" />重置 SMTP 编辑</Button></div>
          <div class="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-3"><p><span class="text-muted-foreground">配置来源：</span>{{ emailSettings?.configuration_source === "database" ? "后台保存" : "部署环境" }}</p><p><span class="text-muted-foreground">投递状态：</span>{{ emailSettings?.smtp_configured ? "配置完整" : "配置待完善" }}</p><p><span class="text-muted-foreground">授权码：</span>{{ emailSettings?.smtp_password_configured ? "已保存" : "未保存" }}</p></div>
          <div class="flex flex-col gap-3 sm:flex-row"><Input v-model="emailRecipient" type="email" placeholder="recipient@synthetic.example.com" aria-label="测试邮件收件人" /><Button :disabled="emailTestBusy || !emailRecipient.trim()" @click="sendEmailTest"><Send class="mr-2 size-4" />发送测试邮件</Button></div>
        </div>
        <p v-if="emailMessage" class="mt-3 text-sm text-primary">{{ emailMessage }}</p><p v-if="emailError" class="mt-3 text-sm text-destructive">{{ emailError }}</p>
      </section>

      <section class="glass-panel flex flex-wrap justify-end gap-3 p-6"><Button type="button" variant="outline" :disabled="loading || mutationBusy" @click="resetCurrentEdits"><RotateCcw class="mr-2 size-4" />重置当前编辑</Button><Button :disabled="loading || mutationBusy" @click="saveSettings"><Save class="mr-2 size-4" />保存设置</Button></section>
    </div>
  </section>
</template>
