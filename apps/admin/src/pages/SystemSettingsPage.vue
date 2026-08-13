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
  type UserLevelDefinition,
} from "@password-detective/api-contract";
import {
  ArrowDownUp,
  CheckCircle2,
  FileClock,
  History,
  KeyRound,
  MailCheck,
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

const defaultSnapshot: OperationalSettingsSnapshot = {
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
  const snapshot = structuredClone(form.value);
  snapshot.user_levels.sort((left, right) => left.min_growth_points - right.min_growth_points);
  return snapshot;
}

function formatDifferenceValue(
  value: number | string | UserLevelDefinition[] | null,
): string {
  if (value === null) return "未设置";
  if (!Array.isArray(value)) return String(value);
  return value
    .map((item) => `${item.name}(${item.min_growth_points}成长值/${item.daily_reveal_quota}次)`)
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
            通过不可变版本完成草稿、差异预览、发布与回滚；发布操作要求管理员 MFA 和一次性再认证，并记录最小披露审计事件。
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

    <section class="glass-panel overflow-hidden p-6 sm:p-8" aria-labelledby="email-delivery-title">
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

    <div class="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
      <div class="space-y-6">
        <section class="glass-panel p-6">
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

        <section class="glass-panel p-6">
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

          <div class="mt-6 space-y-4 border-t border-border/70 pt-5">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 class="font-semibold text-foreground">用户等级与权益</h3>
                <p class="mt-1 text-sm text-muted-foreground">
                  成长值门槛必须唯一并按升序排列；首级门槛固定为 0。发布后会重建全部用户等级投影。
                </p>
              </div>
              <Button type="button" variant="outline" size="sm" @click="addUserLevel">
                <Plus class="mr-2 size-4" />新增等级
              </Button>
            </div>

            <article
              v-for="(level, index) in form.user_levels"
              :key="`${level.code}-${index}`"
              class="rounded-xl border border-border/80 bg-background/70 p-4"
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
              <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
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
                <div class="space-y-2 sm:col-span-2">
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

          <Button class="mt-5" :disabled="mutationBusy" @click="createDraft">
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

        <section class="glass-panel p-6">
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
  </section>
</template>
