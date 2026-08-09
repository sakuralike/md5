<script setup lang="ts">
import {
  ApiError,
  type OperationalSettingsSnapshot,
  type SettingChangeReasonCode,
  type SettingVersionDetail,
  type SettingVersionSummary,
  type SettingVersionStatus,
} from "@password-detective/api-contract";
import {
  ArrowDownUp,
  CheckCircle2,
  FileClock,
  History,
  RefreshCw,
  Rocket,
  RotateCcw,
  Save,
  Settings2,
  ShieldCheck,
} from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
  getSettingVersion,
  listSettingVersions,
  publishSettingVersion,
  rollbackSettingVersion,
} from "../services/settings";
import { reauthenticateAdmin } from "../services/users";
import { useAdminAuthStore } from "../stores/auth";

const defaultSnapshot: OperationalSettingsSnapshot = {
  daily_reveal_quota: 20,
  reauthentication_ttl_minutes: 5,
  privacy_deletion_grace_hours: 72,
  desktop_min_client_version: "1.0.0",
  desktop_update_download_cache_seconds: 3600,
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
const form = ref<OperationalSettingsSnapshot>({ ...defaultSnapshot });

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
  form.value = { ...snapshot };
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
        snapshot: { ...form.value },
      },
      auth.accessToken,
      crypto.randomUUID(),
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
  if (!currentPassword.value || totpCode.value.length !== 6) {
    throw new Error("发布或回滚前必须输入当前密码与 6 位 TOTP 动态码");
  }
  const response = await reauthenticateAdmin(
    {
      currentPassword: currentPassword.value,
      totpCode: totpCode.value,
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
      crypto.randomUUID(),
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
      crypto.randomUUID(),
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

onMounted(() => void loadVersions());
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
        <Button variant="outline" :disabled="loading" @click="loadVersions()">
          <RefreshCw class="mr-2 size-4" :class="{ 'animate-spin': loading }" />刷新版本
        </Button>
      </div>
    </header>

    <div v-if="error" class="rounded-2xl border border-rose-200 bg-rose-50/90 px-4 py-3 text-sm text-rose-700">
      {{ error }}
    </div>
    <div v-if="success" class="rounded-2xl border border-emerald-200 bg-emerald-50/90 px-4 py-3 text-sm text-emerald-700">
      {{ success }}
    </div>

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
                <SelectTrigger><SelectValue placeholder="选择原因" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="security_hardening">安全加固</SelectItem>
                  <SelectItem value="capacity_adjustment">容量调整</SelectItem>
                  <SelectItem value="product_policy">产品策略</SelectItem>
                  <SelectItem value="incident_response">事件响应</SelectItem>
                </SelectContent>
              </Select>
            </div>
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
                <code class="rounded bg-slate-100 px-2 py-1 text-slate-500">{{ difference.previous ?? "未设置" }}</code>
                <span class="text-slate-400">→</span>
                <code class="rounded bg-sky-50 px-2 py-1 text-sky-700">{{ difference.current }}</code>
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
              <Label for="settings-totp">TOTP 动态码</Label>
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
