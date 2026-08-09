<script setup lang="ts">
import {
  ApiError,
  type RiskAlertDetail,
  type RiskAlertNotification,
  type RiskAlertNotificationKind,
  type RiskAlertNotificationMetricsResponse,
  type RiskAlertNotificationStatus,
  type RiskAlertOperator,
  type RiskAlertResolutionCode,
  type RiskAlertSlaState,
  type RiskAlertStatus,
  type RiskAlertSummary,
} from "@password-detective/api-contract";
import { computed, onMounted, ref } from "vue";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Checkbox } from "../components/ui/checkbox";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { Textarea } from "../components/ui/textarea";
import {
  assignRiskAlert,
  createRiskAlertAssignmentKey,
  createRiskAlertNotificationReplayKey,
  createRiskAlertTransitionKey,
  getRiskAlert,
  getRiskAlertNotificationMetrics,
  listRiskAlertNotifications,
  listRiskAlertOperators,
  listRiskAlerts,
  replayRiskAlertNotification,
  transitionRiskAlert,
} from "../services/riskAlerts";
import { useAdminAuthStore } from "../stores/auth";

const auth = useAdminAuthStore();
const alerts = ref<RiskAlertSummary[]>([]);
const operators = ref<RiskAlertOperator[]>([]);
const selected = ref<RiskAlertDetail | null>(null);
const notificationMetrics = ref<RiskAlertNotificationMetricsResponse | null>(null);
const failedDeliveries = ref<RiskAlertNotification[]>([]);
const statusFilter = ref<RiskAlertStatus | "all">("open");
const assigneeFilter = ref("all");
const overdueOnly = ref(false);
const query = ref("");
const total = ref(0);
const loading = ref(false);
const busy = ref(false);
const error = ref("");
const message = ref("");
const resolutionNote = ref("");
const assigneeId = ref("");
const assignmentNote = ref("");
const replayReason = ref("通知通道恢复，管理员手动重放");

const statusLabels: Record<RiskAlertStatus, string> = {
  open: "待响应",
  acknowledged: "核查中",
  resolved: "已解决",
};
const slaLabels: Record<RiskAlertSlaState, string> = {
  within_sla: "SLA 内",
  acknowledgement_overdue: "响应超时",
  resolution_overdue: "解决超时",
  met: "按时完成",
  breached: "曾发生超时",
};
const notificationLabels: Record<RiskAlertNotificationKind, string> = {
  detected: "检测通知",
  assigned: "指派通知",
  acknowledgement_overdue: "响应超时通知",
  resolution_overdue: "解决超时通知",
  resolved: "解决通知",
  reopened: "重开通知",
};
const notificationStatusLabels: Record<RiskAlertNotificationStatus, string> = {
  pending: "待发送",
  sent: "已发送",
  failed: "发送失败",
};

const actions = computed(() => {
  const item = selected.value;
  if (!item) return [];
  const result: Array<{
    target: RiskAlertStatus;
    code: RiskAlertResolutionCode;
    label: string;
    danger?: boolean;
  }> = [];
  if (item.status === "open") {
    result.push({
      target: "acknowledged",
      code: "admin.investigation_started",
      label: "开始核查",
    });
  }
  if (item.status === "open" || item.status === "acknowledged") {
    result.push(
      { target: "resolved", code: "admin.mitigated", label: "确认已处置" },
      {
        target: "resolved",
        code: "admin.false_positive",
        label: "标记误报",
        danger: true,
      },
    );
  } else {
    result.push({ target: "open", code: "admin.reopened", label: "重新开启" });
  }
  return result;
});

function token(): string {
  if (!auth.accessToken) throw new Error("管理会话已失效，请重新登录");
  return auth.accessToken;
}

function describeError(value: unknown): string {
  if (value instanceof ApiError) return `${value.body.message}（${value.body.code}）`;
  return value instanceof Error ? value.message : "操作失败";
}

function formatTime(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(
    new Date(value),
  );
}

function shortId(value: string): string {
  return value.length > 20 ? `${value.slice(0, 9)}…${value.slice(-7)}` : value;
}

function formatDuration(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 60) return `${seconds} 秒`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟`;
  return `${Math.floor(seconds / 3600)} 小时 ${Math.floor((seconds % 3600) / 60)} 分钟`;
}

function operatorName(operatorId: string | null): string {
  if (!operatorId) return "未指派";
  return operators.value.find((operator) => operator.id === operatorId)?.username ?? shortId(operatorId);
}

async function loadOperators(): Promise<void> {
  operators.value = await listRiskAlertOperators(token());
}

async function loadNotificationOperations(): Promise<void> {
  const [metrics, failures] = await Promise.all([
    getRiskAlertNotificationMetrics(token()),
    listRiskAlertNotifications({ status: "failed", pageSize: 10 }, token()),
  ]);
  notificationMetrics.value = metrics;
  failedDeliveries.value = failures.items;
}

async function loadAlerts(selectFirst = false): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const response = await listRiskAlerts(
      {
        kind: "failure_surge",
        severity: "high",
        status: statusFilter.value === "all" ? "" : statusFilter.value,
        assignedToId: assigneeFilter.value === "all" ? "" : assigneeFilter.value,
        overdue: overdueOnly.value ? true : undefined,
        query: query.value,
        page: 1,
        pageSize: 50,
      },
      token(),
    );
    alerts.value = response.items;
    total.value = response.total;
    if (selectFirst && response.items[0]) await openAlert(response.items[0].id);
    if (selected.value && !response.items.some((item) => item.id === selected.value?.id)) {
      selected.value = null;
    }
  } catch (value) {
    error.value = describeError(value);
  } finally {
    loading.value = false;
  }
}

async function openAlert(alertId: string): Promise<void> {
  error.value = "";
  message.value = "";
  try {
    selected.value = await getRiskAlert(alertId, token());
    assigneeId.value = selected.value.assigned_to_id ?? "";
    assignmentNote.value = "";
  } catch (value) {
    error.value = describeError(value);
  }
}

async function applyAssignment(): Promise<void> {
  if (!selected.value || !assigneeId.value) return;
  const alertId = selected.value.id;
  busy.value = true;
  error.value = "";
  message.value = "";
  try {
    await assignRiskAlert(
      alertId,
      {
        assignee_id: assigneeId.value,
        assignment_note: assignmentNote.value.trim() || null,
      },
      token(),
      createRiskAlertAssignmentKey(),
    );
    assignmentNote.value = "";
    await Promise.all([loadAlerts(), loadNotificationOperations()]);
    await openAlert(alertId);
    message.value = "告警负责人已更新，指派事件与通知已进入闭环。";
  } catch (value) {
    error.value = describeError(value);
  } finally {
    busy.value = false;
  }
}

async function replayDelivery(notificationId: string, alertId: string): Promise<void> {
  const reason = replayReason.value.trim();
  if (reason.length < 3) {
    error.value = "请填写至少 3 个字符的重放原因。";
    return;
  }
  busy.value = true;
  error.value = "";
  message.value = "";
  try {
    await replayRiskAlertNotification(
      notificationId,
      { reason },
      token(),
      createRiskAlertNotificationReplayKey(),
    );
    await Promise.all([loadAlerts(), loadNotificationOperations()]);
    if (selected.value?.id === alertId) await openAlert(alertId);
    message.value = "失败通知已重置为待发送，后台工作进程将继续投递。";
  } catch (value) {
    error.value = describeError(value);
  } finally {
    busy.value = false;
  }
}

async function applyAction(action: (typeof actions.value)[number]): Promise<void> {
  if (!selected.value) return;
  const alertId = selected.value.id;
  busy.value = true;
  error.value = "";
  message.value = "";
  try {
    await transitionRiskAlert(
      alertId,
      {
        target_status: action.target,
        resolution_code: action.code,
        resolution_note: resolutionNote.value.trim() || null,
      },
      token(),
      createRiskAlertTransitionKey(),
    );
    resolutionNote.value = "";
    await Promise.all([loadAlerts(), loadNotificationOperations()]);
    await openAlert(alertId);
    message.value = `已完成“${action.label}”，处置事件已写入不可变时间线。`;
  } catch (value) {
    error.value = describeError(value);
  } finally {
    busy.value = false;
  }
}

onMounted(async () => {
  try {
    await Promise.all([loadOperators(), loadNotificationOperations()]);
    await loadAlerts(true);
  } catch (value) {
    error.value = describeError(value);
  }
});
</script>

<template>
  <section class="space-y-5">
    <header class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div class="space-y-2">
        <p class="text-xs font-semibold uppercase tracking-[0.18em] text-destructive">
          M4 · RISK OPERATIONS
        </p>
        <h1 class="text-2xl font-semibold tracking-tight">风险告警</h1>
        <p class="max-w-3xl text-sm leading-6 text-muted-foreground">
          按版本化 SLA 完成检测、指派、响应、解决和通知闭环；页面只展示最小化聚合证据。
        </p>
      </div>
      <Badge variant="secondary">{{ total }} 条</Badge>
    </header>

    <form
      class="grid gap-4 rounded-lg border bg-card p-4 text-card-foreground shadow-sm md:grid-cols-2 xl:grid-cols-[minmax(0,0.8fr)_minmax(0,1fr)_auto_minmax(16rem,1.4fr)_auto] xl:items-end"
      @submit.prevent="loadAlerts(true)"
    >
      <Label class="grid gap-2">
        状态
        <Select v-model="statusFilter">
          <SelectTrigger><SelectValue placeholder="全部状态" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部</SelectItem>
            <SelectItem value="open">待响应</SelectItem>
            <SelectItem value="acknowledged">核查中</SelectItem>
            <SelectItem value="resolved">已解决</SelectItem>
          </SelectContent>
        </Select>
      </Label>
      <Label class="grid gap-2">
        负责人
        <Select v-model="assigneeFilter">
          <SelectTrigger><SelectValue placeholder="全部负责人" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部</SelectItem>
            <SelectItem v-for="operator in operators" :key="operator.id" :value="operator.id">
              {{ operator.username }}
            </SelectItem>
          </SelectContent>
        </Select>
      </Label>
      <Label class="flex min-h-9 items-center gap-2 xl:pb-2">
        <Checkbox v-model="overdueOnly" />
        仅看超时
      </Label>
      <Label class="grid gap-2">
        候选或告警 ID
        <Input v-model="query" maxlength="128" placeholder="输入合成候选 ID" />
      </Label>
      <Button type="submit" :disabled="loading">
        {{ loading ? "加载中…" : "筛选" }}
      </Button>
    </form>

    <section v-if="notificationMetrics" class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="通知投递指标">
      <article class="space-y-2 rounded-lg border bg-card p-4 shadow-sm">
        <span class="text-sm font-medium text-muted-foreground">待发送</span>
        <strong class="block text-2xl">{{ notificationMetrics.pending_count }}</strong>
      </article>
      <article class="space-y-2 rounded-lg border bg-card p-4 shadow-sm">
        <span class="text-sm font-medium text-muted-foreground">已发送</span>
        <strong class="block text-2xl">{{ notificationMetrics.sent_count }}</strong>
      </article>
      <article
        class="space-y-2 rounded-lg border bg-card p-4 shadow-sm"
        :class="notificationMetrics.failed_count > 0 ? 'border-destructive/50 bg-destructive/10 text-destructive' : ''"
      >
        <span class="text-sm font-medium">失败 / 24 小时</span>
        <strong class="block text-2xl">{{ notificationMetrics.failed_count }} / {{ notificationMetrics.failed_last_24_hours }}</strong>
      </article>
      <article class="space-y-2 rounded-lg border bg-card p-4 shadow-sm">
        <span class="text-sm font-medium text-muted-foreground">最老待发送</span>
        <strong class="block text-2xl">{{ formatDuration(notificationMetrics.oldest_pending_seconds) }}</strong>
      </article>
    </section>

    <section v-if="failedDeliveries.length" class="space-y-4 rounded-lg border bg-card p-5 shadow-sm sm:p-6">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div class="space-y-1">
          <p class="text-xs font-semibold uppercase tracking-[0.18em] text-destructive">DELIVERY DEAD LETTERS</p>
          <h2 class="text-lg font-semibold tracking-tight">失败通知队列</h2>
        </div>
        <Badge variant="destructive">{{ notificationMetrics?.failed_count ?? failedDeliveries.length }} 条</Badge>
      </div>
      <Label class="grid gap-2">
        重放原因（禁止填写密码、令牌、邮箱或 IP）
        <Input v-model="replayReason" maxlength="500" />
      </Label>
      <ol class="space-y-3 border-l pl-5">
        <li v-for="notification in failedDeliveries" :key="notification.id" class="space-y-2">
          <strong>{{ notificationLabels[notification.kind] }} · {{ notification.provider || "未分配通道" }}</strong>
          <p class="text-sm text-muted-foreground">
            告警
            <Button type="button" variant="link" class="h-auto p-0 text-destructive" @click="openAlert(notification.alert_id)">
              {{ shortId(notification.alert_id) }}
            </Button>
            · 尝试 {{ notification.attempts }} 次 · 重放 {{ notification.replay_count }} 次
          </p>
          <small class="block text-muted-foreground">{{ formatTime(notification.failed_at) }} · {{ notification.last_error_code || "未记录错误码" }}</small>
          <Button
            type="button"
            variant="outline"
            size="sm"
            :disabled="busy || replayReason.trim().length < 3"
            @click="replayDelivery(notification.id, notification.alert_id)"
          >
            重放
          </Button>
        </li>
      </ol>
    </section>

    <p
      v-if="error"
      class="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive"
      role="alert"
    >
      {{ error }}
    </p>
    <p
      v-if="message"
      class="rounded-md border border-primary/30 bg-primary/10 px-4 py-3 text-sm text-primary"
      role="status"
    >
      {{ message }}
    </p>

    <div class="grid items-start gap-5 lg:grid-cols-[minmax(18.75rem,0.72fr)_minmax(0,1.28fr)]">
      <aside class="grid max-h-[calc(100vh-14rem)] gap-3 overflow-y-auto rounded-lg border bg-card p-4 shadow-sm lg:sticky lg:top-4">
        <Button
          v-for="alert in alerts"
          :key="alert.id"
          type="button"
          variant="outline"
          class="h-auto w-full justify-start whitespace-normal p-4 text-left"
          :class="selected?.id === alert.id ? 'border-destructive/60 bg-destructive/10' : ''"
          @click="openAlert(alert.id)"
        >
          <span class="grid w-full gap-2">
            <span class="flex items-center justify-between gap-3">
              <strong>{{ statusLabels[alert.status] }}</strong>
              <Badge
                :variant="['acknowledgement_overdue', 'resolution_overdue', 'breached'].includes(alert.sla_state) ? 'destructive' : alert.sla_state === 'met' ? 'secondary' : 'outline'"
              >
                {{ slaLabels[alert.sla_state] }}
              </Badge>
            </span>
            <code class="break-all text-xs text-muted-foreground">{{ shortId(alert.candidate_id) }}</code>
            <small class="text-muted-foreground">{{ alert.independent_failure_count }} 个独立失败 · {{ operatorName(alert.assigned_to_id) }}</small>
            <small class="text-muted-foreground">响应截止 {{ formatTime(alert.acknowledge_due_at) }}</small>
          </span>
        </Button>
        <p v-if="!loading && alerts.length === 0" class="py-8 text-center text-sm text-muted-foreground">
          当前筛选条件下没有风险告警。
        </p>
      </aside>

      <article v-if="selected" class="space-y-6 rounded-lg border bg-card p-5 text-card-foreground shadow-sm sm:p-6">
        <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div class="space-y-1">
            <p class="text-xs font-semibold uppercase tracking-[0.18em] text-destructive">HIGH · FAILURE SURGE</p>
            <h2 class="break-all text-lg font-semibold tracking-tight">{{ shortId(selected.id) }}</h2>
          </div>
          <div class="flex flex-wrap gap-2 sm:justify-end">
            <Badge :variant="selected.status === 'open' ? 'destructive' : selected.status === 'resolved' ? 'secondary' : 'outline'">
              {{ statusLabels[selected.status] }}
            </Badge>
            <Badge
              :variant="['acknowledgement_overdue', 'resolution_overdue', 'breached'].includes(selected.sla_state) ? 'destructive' : selected.sla_state === 'met' ? 'secondary' : 'outline'"
            >
              {{ slaLabels[selected.sla_state] }}
            </Badge>
          </div>
        </div>

        <dl class="grid gap-4 sm:grid-cols-2">
          <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">候选 ID</dt><dd><code class="break-all text-sm">{{ selected.candidate_id }}</code></dd></div>
          <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">检测规则</dt><dd><code class="break-all text-sm">{{ selected.rule_version }}</code></dd></div>
          <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">SLA 规则</dt><dd><code class="break-all text-sm">{{ selected.sla_rule_version }}</code></dd></div>
          <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">负责人</dt><dd>{{ selected.assigned_to_username || "未指派" }}</dd></div>
          <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">独立失败数</dt><dd>{{ selected.independent_failure_count }}</dd></div>
          <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">失败权重</dt><dd>{{ selected.failure_weight }}</dd></div>
          <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">响应截止</dt><dd>{{ formatTime(selected.acknowledge_due_at) }}</dd></div>
          <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">首次响应</dt><dd>{{ formatTime(selected.acknowledged_at) }}</dd></div>
          <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">解决截止</dt><dd>{{ formatTime(selected.resolve_due_at) }}</dd></div>
          <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">解决时间</dt><dd>{{ formatTime(selected.resolved_at) }}</dd></div>
          <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">观察窗口开始</dt><dd>{{ formatTime(selected.window_started_at) }}</dd></div>
          <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">观察窗口结束</dt><dd>{{ formatTime(selected.window_ended_at) }}</dd></div>
          <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">处理结果</dt><dd class="break-all">{{ selected.resolution_code || "—" }}</dd></div>
        </dl>

        <section v-if="selected.resolution_note" class="space-y-2">
          <h3 class="font-semibold">处理说明</h3>
          <p class="whitespace-pre-wrap rounded-md bg-muted/50 p-4 text-sm leading-6">{{ selected.resolution_note }}</p>
        </section>

        <section v-if="selected.status !== 'resolved'" class="space-y-4 rounded-lg border bg-muted/30 p-4">
          <h3 class="font-semibold">负责人指派</h3>
          <Label class="grid gap-2">
            具备 MFA 的值班人员
            <Select v-model="assigneeId">
              <SelectTrigger><SelectValue placeholder="请选择负责人" /></SelectTrigger>
              <SelectContent>
                <SelectItem v-for="operator in operators" :key="operator.id" :value="operator.id">
                  {{ operator.username }} · {{ operator.role }}
                </SelectItem>
              </SelectContent>
            </Select>
          </Label>
          <Label class="grid gap-2">
            指派说明（不要粘贴敏感标识）
            <Textarea v-model="assignmentNote" maxlength="1000" rows="2" />
          </Label>
          <Button
            type="button"
            variant="outline"
            :disabled="busy || !assigneeId || assigneeId === selected.assigned_to_id"
            @click="applyAssignment"
          >
            更新负责人
          </Button>
        </section>

        <section class="space-y-4 rounded-lg border bg-muted/30 p-4">
          <h3 class="font-semibold">告警处置</h3>
          <Label class="grid gap-2">
            处理说明（不要粘贴密码、令牌、IP 或安装标识）
            <Textarea v-model="resolutionNote" maxlength="1000" rows="3" />
          </Label>
          <div class="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
            <Button
              v-for="action in actions"
              :key="action.code"
              type="button"
              :variant="action.danger ? 'destructive' : 'default'"
              :disabled="busy"
              @click="applyAction(action)"
            >
              {{ action.label }}
            </Button>
          </div>
        </section>

        <section class="space-y-3">
          <h3 class="font-semibold">通知投递记录</h3>
          <p v-if="selected.notifications.length === 0" class="text-sm text-muted-foreground">暂无通知记录。</p>
          <ol v-else class="space-y-3 border-l pl-5">
            <li v-for="notification in selected.notifications" :key="notification.id" class="space-y-2">
              <strong>{{ notificationLabels[notification.kind] }} · {{ notificationStatusLabels[notification.status] }}</strong>
              <p class="text-sm text-muted-foreground">接收人 {{ notification.recipient_username }} · 通道 {{ notification.provider || "待分配" }} · 尝试 {{ notification.attempts }} 次 · 重放 {{ notification.replay_count }} 次</p>
              <small class="block text-muted-foreground">
                {{ formatTime(notification.failed_at || notification.sent_at || notification.available_at) }}
                <template v-if="notification.provider_message_id"> · 回执 {{ shortId(notification.provider_message_id) }}</template>
                <template v-if="notification.last_error_code"> · {{ notification.last_error_code }}</template>
              </small>
              <Button
                v-if="notification.status === 'failed'"
                type="button"
                variant="outline"
                size="sm"
                :disabled="busy || replayReason.trim().length < 3"
                @click="replayDelivery(notification.id, notification.alert_id)"
              >
                重放
              </Button>
            </li>
          </ol>
        </section>

        <section class="space-y-3">
          <h3 class="font-semibold">不可变告警时间线</h3>
          <ol class="space-y-3 border-l pl-5">
            <li v-for="event in selected.events" :key="event.id" class="space-y-1">
              <strong>{{ event.action }}</strong>
              <p class="text-sm">{{ event.previous_status || "检测" }} → {{ event.next_status }} · {{ event.reason_code }}</p>
              <p v-if="event.previous_assignee_id !== event.next_assignee_id" class="text-sm">负责人：{{ operatorName(event.previous_assignee_id) }} → {{ operatorName(event.next_assignee_id) }}</p>
              <p v-if="event.note" class="whitespace-pre-wrap text-sm">{{ event.note }}</p>
              <small class="text-muted-foreground">{{ formatTime(event.created_at) }} · {{ event.request_id || "系统检测" }}</small>
            </li>
          </ol>
        </section>
      </article>
      <article v-else class="rounded-lg border bg-card p-8 text-center text-sm text-muted-foreground shadow-sm">
        请选择左侧告警查看详情。
      </article>
    </div>
  </section>
</template>
