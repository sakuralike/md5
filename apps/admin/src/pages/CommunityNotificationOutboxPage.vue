<script setup lang="ts">
import {
  ApiError,
  type AdminCommunityNotificationOutboxItem,
  type AdminCommunityNotificationOutboxMetrics,
  type CommunityNotificationKind,
  type CommunityNotificationOutboxStatus,
} from "@password-detective/api-contract";
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
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import {
  createCommunityNotificationReplayKey,
  getCommunityNotificationOutboxMetrics,
  listCommunityNotificationOutbox,
  replayCommunityNotificationOutbox,
} from "../services/communityNotificationOutbox";
import { reauthenticateAdmin } from "../services/users";
import { useAdminAuthStore } from "../stores/auth";

type StatusFilter = CommunityNotificationOutboxStatus | "all";
type KindFilter = CommunityNotificationKind | "all";

const auth = useAdminAuthStore();
const metrics = ref<AdminCommunityNotificationOutboxMetrics | null>(null);
const items = ref<AdminCommunityNotificationOutboxItem[]>([]);
const total = ref(0);
const statusFilter = ref<StatusFilter>("failed");
const kindFilter = ref<KindFilter>("all");
const errorCode = ref("");
const selectedId = ref("");
const replayReason = ref("");
const currentPassword = ref("");
const totpCode = ref("");
const loading = ref(true);
const busy = ref(false);
const error = ref("");
const success = ref("");

const selected = computed(() => items.value.find((item) => item.id === selectedId.value) ?? null);
const canReplay = computed(() =>
  selected.value?.status === "failed"
  && replayReason.value.trim().length >= 3
  && currentPassword.value.length > 0
  && /^\d{6,8}$/.test(totpCode.value),
);

onMounted(() => {
  void refresh();
});

function token(): string {
  if (!auth.accessToken) throw new Error("管理会话已失效，请重新登录");
  return auth.accessToken;
}

function describeError(value: unknown): string {
  if (value instanceof ApiError) return `${value.body.message}（${value.body.code}）`;
  return value instanceof Error ? value.message : "操作失败";
}

async function refresh(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const [nextMetrics, response] = await Promise.all([
      getCommunityNotificationOutboxMetrics(token()),
      listCommunityNotificationOutbox(
        {
          ...(statusFilter.value === "all" ? {} : { status: statusFilter.value }),
          ...(kindFilter.value === "all" ? {} : { kind: kindFilter.value }),
          errorCode: errorCode.value,
          pageSize: 50,
        },
        token(),
      ),
    ]);
    metrics.value = nextMetrics;
    items.value = response.items;
    total.value = response.total;
    if (selectedId.value && !items.value.some((item) => item.id === selectedId.value)) {
      selectedId.value = "";
    }
  } catch (caught) {
    error.value = describeError(caught);
  } finally {
    loading.value = false;
  }
}

async function replaySelected(): Promise<void> {
  if (!selected.value || !canReplay.value) return;
  busy.value = true;
  error.value = "";
  success.value = "";
  const eventId = selected.value.id;
  try {
    const grant = await reauthenticateAdmin(
      {
        currentPassword: currentPassword.value,
        totpCode: totpCode.value,
        purpose: "admin_community_notification_ops",
      },
      token(),
    );
    const response = await replayCommunityNotificationOutbox(
      eventId,
      { reason: replayReason.value.trim(), reauthToken: grant.reauth_token },
      token(),
      createCommunityNotificationReplayKey(),
    );
    success.value = `事件 ${shortId(response.event.id)} 已重置为待投递，Worker 将重新校验偏好、屏蔽和内容可见性。`;
    replayReason.value = "";
    selectedId.value = "";
    await refresh();
  } catch (caught) {
    error.value = describeError(caught);
  } finally {
    currentPassword.value = "";
    totpCode.value = "";
    busy.value = false;
  }
}

function formatTime(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(
    new Date(value),
  );
}

function formatDuration(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 60) return `${seconds} 秒`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟`;
  return `${Math.floor(seconds / 3600)} 小时`;
}

function shortId(value: string): string {
  return value.length > 20 ? `${value.slice(0, 8)}…${value.slice(-6)}` : value;
}

function statusLabel(value: CommunityNotificationOutboxStatus): string {
  return { pending: "待投递", delivered: "已投递", failed: "失败" }[value];
}

function kindLabel(value: CommunityNotificationKind): string {
  const labels: Record<CommunityNotificationKind, string> = {
    mention: "提及",
    reply: "回复",
    direct_message: "私信",
    follow: "关注",
    like_summary: "点赞汇总",
    group_application: "群组申请",
    group_decision: "群组审批",
    group_role_change: "群组角色变更",
    plugin_review: "插件审核",
  };
  return labels[value];
}
</script>

<template>
  <section class="space-y-6">
    <header class="rounded-2xl border bg-card p-6 shadow-sm sm:p-8">
      <div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div class="space-y-3">
          <div class="flex flex-wrap gap-2">
            <Badge>社区通知运维</Badge>
            <Badge variant="outline">管理员 + TOTP + 一次性再认证</Badge>
          </div>
          <h1 class="text-3xl font-semibold tracking-tight">社区通知 Outbox 工作台</h1>
          <p class="max-w-3xl text-muted-foreground">
            查看社区实时通知的积压与失败事件，并在审计原因、幂等键和新鲜 MFA 再认证保护下执行单条重放。重放不会直接投递，而是交回 Worker 重新执行安全校验。
          </p>
        </div>
        <Button type="button" variant="outline" :disabled="loading || busy" @click="refresh">
          {{ loading ? "刷新中…" : "刷新数据" }}
        </Button>
      </div>
    </header>

    <div v-if="error" role="alert" class="rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
      <strong class="font-semibold">操作失败：</strong>{{ error }}
    </div>
    <div v-if="success" role="status" class="rounded-xl border border-primary/30 bg-primary/5 p-4 text-sm">
      {{ success }}
    </div>

    <section class="grid gap-4 sm:grid-cols-2 xl:grid-cols-5" aria-label="社区通知投递指标">
      <article class="rounded-xl border bg-card p-5 shadow-sm">
        <p class="text-sm text-muted-foreground">待投递</p>
        <p class="mt-2 text-3xl font-semibold">{{ metrics?.pending_count ?? "—" }}</p>
      </article>
      <article class="rounded-xl border bg-card p-5 shadow-sm">
        <p class="text-sm text-muted-foreground">失败总数</p>
        <p class="mt-2 text-3xl font-semibold text-destructive">{{ metrics?.failed_count ?? "—" }}</p>
      </article>
      <article class="rounded-xl border bg-card p-5 shadow-sm">
        <p class="text-sm text-muted-foreground">24 小时失败</p>
        <p class="mt-2 text-3xl font-semibold">{{ metrics?.failed_last_24_hours ?? "—" }}</p>
      </article>
      <article class="rounded-xl border bg-card p-5 shadow-sm">
        <p class="text-sm text-muted-foreground">已到期待处理</p>
        <p class="mt-2 text-3xl font-semibold">{{ metrics?.retry_due_count ?? "—" }}</p>
      </article>
      <article class="rounded-xl border bg-card p-5 shadow-sm">
        <p class="text-sm text-muted-foreground">最老积压</p>
        <p class="mt-2 text-xl font-semibold">{{ formatDuration(metrics?.oldest_pending_seconds ?? null) }}</p>
      </article>
    </section>

    <section class="grid gap-4 sm:grid-cols-2 xl:grid-cols-5" aria-label="邮件摘要投递指标">
      <article class="rounded-xl border bg-card p-5 shadow-sm">
        <p class="text-sm text-muted-foreground">邮件摘要待发送</p>
        <p class="mt-2 text-3xl font-semibold">{{ metrics?.email_digest_pending_count ?? "—" }}</p>
      </article>
      <article class="rounded-xl border bg-card p-5 shadow-sm">
        <p class="text-sm text-muted-foreground">邮件摘要已发送</p>
        <p class="mt-2 text-3xl font-semibold">{{ metrics?.email_digest_sent_count ?? "—" }}</p>
      </article>
      <article class="rounded-xl border bg-card p-5 shadow-sm">
        <p class="text-sm text-muted-foreground">邮件摘要失败</p>
        <p class="mt-2 text-3xl font-semibold text-destructive">{{ metrics?.email_digest_failed_count ?? "—" }}</p>
      </article>
      <article class="rounded-xl border bg-card p-5 shadow-sm">
        <p class="text-sm text-muted-foreground">邮件摘要已抑制</p>
        <p class="mt-2 text-3xl font-semibold">{{ metrics?.email_digest_suppressed_count ?? "—" }}</p>
      </article>
      <article class="rounded-xl border bg-card p-5 shadow-sm">
        <p class="text-sm text-muted-foreground">最近摘要发送</p>
        <p class="mt-2 text-xl font-semibold">{{ formatTime(metrics?.email_digest_last_sent_at ?? null) }}</p>
      </article>
    </section>

    <section class="rounded-2xl border bg-card p-5 shadow-sm">
      <div class="grid gap-4 md:grid-cols-4">
        <div class="space-y-2">
          <Label for="outbox-status">投递状态</Label>
          <Select v-model="statusFilter">
            <SelectTrigger id="outbox-status"><SelectValue placeholder="全部状态" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部状态</SelectItem>
              <SelectItem value="failed">失败</SelectItem>
              <SelectItem value="pending">待投递</SelectItem>
              <SelectItem value="delivered">已投递</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="space-y-2">
          <Label for="outbox-kind">通知类型</Label>
          <Select v-model="kindFilter">
            <SelectTrigger id="outbox-kind"><SelectValue placeholder="全部类型" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部类型</SelectItem>
              <SelectItem value="mention">提及</SelectItem>
              <SelectItem value="reply">回复</SelectItem>
              <SelectItem value="direct_message">私信</SelectItem>
              <SelectItem value="follow">关注</SelectItem>
              <SelectItem value="like_summary">点赞汇总</SelectItem>
              <SelectItem value="group_application">群组申请</SelectItem>
              <SelectItem value="group_decision">群组审批</SelectItem>
              <SelectItem value="group_role_change">群组角色变更</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="space-y-2">
          <Label for="outbox-error">错误代码</Label>
          <Input id="outbox-error" v-model="errorCode" maxlength="128" placeholder="例如 community.notification_dispatch_failed" />
        </div>
        <div class="flex items-end">
          <Button type="button" class="w-full" :disabled="loading" @click="refresh">应用筛选</Button>
        </div>
      </div>
    </section>

    <div class="grid gap-6 2xl:grid-cols-[minmax(0,1fr)_420px]">
      <section class="overflow-hidden rounded-2xl border bg-card shadow-sm">
        <div class="flex items-center justify-between border-b p-5">
          <div>
            <h2 class="font-semibold">投递事件</h2>
            <p class="text-sm text-muted-foreground">当前筛选共 {{ total }} 条，最多展示 50 条。</p>
          </div>
        </div>
        <div class="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>事件</TableHead><TableHead>通知</TableHead><TableHead>状态</TableHead>
                <TableHead>尝试</TableHead><TableHead>错误</TableHead><TableHead>更新时间</TableHead><TableHead class="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow v-for="item in items" :key="item.id">
                <TableCell class="font-mono text-xs">{{ shortId(item.id) }}</TableCell>
                <TableCell>
                  <p class="font-medium">{{ kindLabel(item.kind) }}</p>
                  <p class="text-xs text-muted-foreground">{{ item.actor_username }} → {{ item.recipient_username }}</p>
                </TableCell>
                <TableCell><Badge :variant="item.status === 'failed' ? 'destructive' : 'outline'">{{ statusLabel(item.status) }}</Badge></TableCell>
                <TableCell>{{ item.attempts }} / 重放 {{ item.replay_count }}</TableCell>
                <TableCell class="max-w-64 break-all text-xs">{{ item.last_error_code ?? "—" }}</TableCell>
                <TableCell>{{ formatTime(item.updated_at) }}</TableCell>
                <TableCell class="text-right">
                  <Button type="button" size="sm" variant="outline" :disabled="item.status !== 'failed'" @click="selectedId = item.id">选择重放</Button>
                </TableCell>
              </TableRow>
              <TableRow v-if="!loading && items.length === 0">
                <TableCell colspan="7" class="py-12 text-center text-muted-foreground">当前筛选没有投递事件。</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>
      </section>

      <aside class="h-fit space-y-5 rounded-2xl border bg-card p-5 shadow-sm 2xl:sticky 2xl:top-28">
        <div>
          <h2 class="font-semibold">受控单条重放</h2>
          <p class="mt-1 text-sm text-muted-foreground">仅失败事件可操作；一次性凭据在每次重放后立即失效。</p>
        </div>
        <div v-if="selected" class="space-y-2 rounded-xl border bg-muted/40 p-4 text-sm">
          <p><span class="text-muted-foreground">事件：</span><span class="font-mono">{{ shortId(selected.id) }}</span></p>
          <p><span class="text-muted-foreground">类型：</span>{{ kindLabel(selected.kind) }}</p>
          <p><span class="text-muted-foreground">错误：</span>{{ selected.last_error_code ?? "—" }}</p>
          <p><span class="text-muted-foreground">失败时间：</span>{{ formatTime(selected.failed_at) }}</p>
        </div>
        <p v-else class="rounded-xl border border-dashed p-4 text-sm text-muted-foreground">请先从左侧选择一条失败事件。</p>
        <div class="space-y-2">
          <Label for="replay-reason">重放原因</Label>
          <Textarea id="replay-reason" v-model="replayReason" maxlength="500" placeholder="说明故障已排除或为何允许重新投递" />
        </div>
        <div class="space-y-2">
          <Label for="replay-password">当前密码</Label>
          <Input id="replay-password" v-model="currentPassword" type="password" autocomplete="current-password" />
        </div>
        <div class="space-y-2">
          <Label for="replay-totp">TOTP 动态码</Label>
          <Input id="replay-totp" v-model="totpCode" inputmode="numeric" maxlength="8" autocomplete="one-time-code" placeholder="6 至 8 位数字" />
        </div>
        <Button type="button" class="w-full" :disabled="busy || !canReplay" @click="replaySelected">
          {{ busy ? "验证并提交中…" : "完成再认证并重放" }}
        </Button>
      </aside>
    </div>
  </section>
</template>
