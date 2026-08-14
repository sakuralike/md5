<script setup lang="ts">
import {
  ApiError,
  type TrustCaseDetail,
  type TrustCaseCandidateTargetStatus,
  type TrustCaseKind,
  type TrustCaseNotification,
  type TrustCaseResolutionCode,
  type TrustCaseStatus,
  type TrustCaseSummary,
} from "@password-detective/api-contract";
import { computed, onMounted, ref } from "vue";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
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
  assignTrustCase,
  createTrustCaseAssignKey,
  createTrustCaseNotificationReplayKey,
  createTrustCaseReopenKey,
  createTrustCaseResolveKey,
  createTrustCaseTransitionKey,
  getTrustCase,
  listTrustCases,
  reopenTrustCase,
  replayTrustCaseNotification,
  resolveTrustCase,
  transitionTrustCase,
} from "../services/trustCases";
import { useAdminAuthStore } from "../stores/auth";

const auth = useAdminAuthStore();
const cases = ref<TrustCaseSummary[]>([]);
const selected = ref<TrustCaseDetail | null>(null);
const kindFilter = ref<TrustCaseKind | "all">("all");
const statusFilter = ref<TrustCaseStatus | "all">("open");
const query = ref("");
const total = ref(0);
const loading = ref(false);
const busy = ref(false);
const error = ref("");
const message = ref("");
const resolutionNote = ref("");
const assigneeId = ref("");

const kindLabels: Record<TrustCaseKind, string> = {
  report: "内容举报",
  appeal: "贡献申诉",
  account_appeal: "账号申诉",
};
const statusLabels: Record<TrustCaseStatus, string> = {
  open: "待处理",
  in_review: "处理中",
  resolved: "已解决",
  dismissed: "已驳回",
};

const actions = computed(() => {
  const item = selected.value;
  if (!item) return [];
  const result: Array<{
    target: TrustCaseStatus;
    code: TrustCaseResolutionCode;
    label: string;
    danger?: boolean;
  }> = [];
  if (item.status === "open") {
    result.push({ target: "in_review", code: "admin.review_started", label: "开始处理" });
  }
  if (item.status === "open" || item.status === "in_review") {
    if (item.kind === "account_appeal") {
      result.push(
        { target: "resolved", code: "admin.account_restored", label: "恢复账号" },
        {
          target: "dismissed",
          code: "admin.account_restriction_upheld",
          label: "维持账号限制",
          danger: true,
        },
      );
    } else if (item.kind === "appeal") {
      result.push(
        { target: "resolved", code: "admin.appeal_upheld", label: "支持申诉" },
        { target: "dismissed", code: "admin.appeal_denied", label: "驳回申诉", danger: true },
      );
    } else {
      result.push(
        { target: "resolved", code: "admin.action_taken", label: "确认并已处置" },
        { target: "dismissed", code: "admin.no_violation", label: "确认无违规" },
      );
    }
    result.push({
      target: "dismissed",
      code: "admin.insufficient_evidence",
      label: "证据不足关闭",
      danger: true,
    });
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

function subjectLabel(item: TrustCaseSummary): string {
  if (item.subject_type === "account") return `账号 ${shortId(item.target_user_id ?? "—")}`;
  if (item.subject_type === "risk_alert") return `风险告警 ${shortId(item.risk_alert_id ?? "—")}`;
  return `候选 ${shortId(item.candidate_id ?? "—")}`;
}

async function loadCases(selectFirst = false): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const response = await listTrustCases(
      {
        kind: kindFilter.value === "all" ? "" : kindFilter.value,
        status: statusFilter.value === "all" ? "" : statusFilter.value,
        query: query.value,
        page: 1,
        pageSize: 50,
      },
      token(),
    );
    cases.value = response.items;
    total.value = response.total;
    if (selectFirst && response.items[0]) await openCase(response.items[0].id);
    if (selected.value && !response.items.some((item) => item.id === selected.value?.id)) {
      selected.value = null;
    }
  } catch (value) {
    error.value = describeError(value);
  } finally {
    loading.value = false;
  }
}

async function openCase(caseId: string, preserveFeedback = false): Promise<void> {
  if (!preserveFeedback) {
    error.value = "";
    message.value = "";
  }
  try {
    selected.value = await getTrustCase(caseId, token());
    assigneeId.value = selected.value.assigned_to_id ?? "";
  } catch (value) {
    error.value = describeError(value);
  }
}

async function assignSelectedCase(): Promise<void> {
  if (!selected.value || !assigneeId.value.trim()) return;
  const caseId = selected.value.id;
  busy.value = true;
  error.value = "";
  message.value = "";
  try {
    await assignTrustCase(
      caseId,
      {
        expected_version: selected.value.version,
        assignee_id: assigneeId.value.trim(),
        reason_code: selected.value.assigned_to_id ? "admin.reassigned" : "admin.assigned",
        note: resolutionNote.value.trim() || null,
      },
      token(),
      createTrustCaseAssignKey(),
    );
    resolutionNote.value = "";
    message.value = "已更新案件负责人，指派事件已写入不可变时间线。";
    await loadCases();
    await openCase(caseId, true);
  } catch (value) {
    error.value = describeError(value);
  } finally {
    busy.value = false;
  }
}

async function reopenSelectedCase(): Promise<void> {
  if (!selected.value) return;
  const caseId = selected.value.id;
  busy.value = true;
  error.value = "";
  message.value = "";
  try {
    await reopenTrustCase(
      caseId,
      {
        expected_version: selected.value.version,
        reason_code: "admin.reopened",
        note: resolutionNote.value.trim() || null,
      },
      token(),
      createTrustCaseReopenKey(),
    );
    resolutionNote.value = "";
    message.value = "已重新开启案件，重开事件已写入不可变时间线。";
    await loadCases();
    await openCase(caseId, true);
  } catch (value) {
    error.value = describeError(value);
  } finally {
    busy.value = false;
  }
}

async function applyAction(action: (typeof actions.value)[number]): Promise<void> {
  if (!selected.value) return;
  const caseId = selected.value.id;
  busy.value = true;
  error.value = "";
  message.value = "";
  try {
    if (action.code === "admin.review_started") {
      await transitionTrustCase(
        caseId,
        {
          expected_version: selected.value.version,
          target_status: action.target,
          resolution_code: action.code,
          resolution_note: resolutionNote.value.trim() || null,
        },
        token(),
        createTrustCaseTransitionKey(),
      );
    } else {
      const note = resolutionNote.value.trim();
      if (!note) throw new Error("完成案件处置前必须填写处理说明");
      let candidateTargetStatus: TrustCaseCandidateTargetStatus | null = null;
      if (action.code === "admin.action_taken") candidateTargetStatus = "quarantined";
      if (action.code === "admin.appeal_upheld") candidateTargetStatus = "verified";
      await resolveTrustCase(
        caseId,
        {
          expected_version: selected.value.version,
          resolution_code: action.code,
          resolution_note: note,
          candidate_target_status: candidateTargetStatus,
        },
        token(),
        createTrustCaseResolveKey(),
      );
    }
    resolutionNote.value = "";
    message.value = `已完成“${action.label}”，处理事件和副作用已原子写入。`;
    await loadCases();
    await openCase(caseId, true);
  } catch (value) {
    error.value = describeError(value);
  } finally {
    busy.value = false;
  }
}

async function replayNotification(notification: TrustCaseNotification): Promise<void> {
  if (!selected.value) return;
  const caseId = selected.value.id;
  busy.value = true;
  error.value = "";
  message.value = "";
  try {
    await replayTrustCaseNotification(
      notification.id,
      { reason_code: "admin.manual_replay", note: resolutionNote.value.trim() || null },
      token(),
      createTrustCaseNotificationReplayKey(),
    );
    message.value = "通知已重新进入发送队列。";
    await openCase(caseId, true);
  } catch (value) {
    error.value = describeError(value);
  } finally {
    busy.value = false;
  }
}

onMounted(() => loadCases(true));
</script>

<template>
  <section class="space-y-5">
    <header class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div class="space-y-2">
        <p class="text-xs font-semibold uppercase tracking-[0.18em] text-primary">
          M4 · COMMUNITY TRUST
        </p>
        <h1 class="text-2xl font-semibold tracking-tight">举报与申诉</h1>
        <p class="max-w-3xl text-sm leading-6 text-muted-foreground">
          处理候选内容举报和贡献者申诉；自由文本只进入案件详情和事件时间线，不复制到审计摘要。
        </p>
      </div>
      <Badge variant="secondary">{{ total }} 个案件</Badge>
    </header>

    <form
      class="grid gap-4 rounded-lg border bg-card p-4 text-card-foreground shadow-sm md:grid-cols-[minmax(0,0.75fr)_minmax(0,0.75fr)_minmax(16rem,1.5fr)_auto] md:items-end"
      @submit.prevent="loadCases(true)"
    >
      <Label class="grid gap-2">
        类型
        <Select v-model="kindFilter">
          <SelectTrigger aria-label="案件类型筛选"><SelectValue placeholder="全部类型" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部</SelectItem>
            <SelectItem value="report">举报</SelectItem>
            <SelectItem value="appeal">申诉</SelectItem>
          </SelectContent>
        </Select>
      </Label>
      <Label class="grid gap-2">
        状态
        <Select v-model="statusFilter">
          <SelectTrigger aria-label="案件状态筛选"><SelectValue placeholder="全部状态" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部</SelectItem>
            <SelectItem value="open">待处理</SelectItem>
            <SelectItem value="in_review">处理中</SelectItem>
            <SelectItem value="resolved">已解决</SelectItem>
            <SelectItem value="dismissed">已驳回</SelectItem>
          </SelectContent>
        </Select>
      </Label>
      <Label class="grid gap-2">
        搜索
        <Input v-model="query" maxlength="128" placeholder="案件 ID、候选 ID 或用户名" />
      </Label>
      <Button type="submit" :disabled="loading">
        {{ loading ? "加载中…" : "筛选" }}
      </Button>
    </form>

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

    <div class="grid items-start gap-5 lg:grid-cols-[minmax(17.5rem,0.7fr)_minmax(0,1.3fr)]">
      <aside class="grid max-h-[calc(100vh-14rem)] gap-3 overflow-y-auto rounded-lg border bg-card p-4 shadow-sm lg:sticky lg:top-4">
        <Button
          v-for="item in cases"
          :key="item.id"
          type="button"
          variant="secondary"
          class="h-auto w-full justify-start whitespace-normal border border-transparent p-4 text-left"
          :class="selected?.id === item.id ? 'border-primary ring-1 ring-primary/20' : ''"
          @click="openCase(item.id)"
        >
          <span class="grid w-full gap-2">
            <span class="flex items-center justify-between gap-3">
              <strong>{{ kindLabels[item.kind] }}</strong>
              <Badge
                :variant="item.status === 'open' ? 'destructive' : item.status === 'resolved' ? 'secondary' : 'outline'"
              >
                {{ statusLabels[item.status] }}
              </Badge>
            </span>
            <code class="break-all text-xs text-muted-foreground">{{ shortId(item.id) }}</code>
            <small class="text-muted-foreground">
              {{ item.reporter_username }} · {{ formatTime(item.created_at) }}
            </small>
            <small class="break-all text-muted-foreground">{{ subjectLabel(item) }}</small>
          </span>
        </Button>
        <p v-if="!loading && cases.length === 0" class="py-8 text-center text-sm text-muted-foreground">
          当前筛选条件下没有案件。
        </p>
      </aside>

      <article v-if="selected" class="space-y-6 rounded-lg border bg-card p-5 text-card-foreground shadow-sm sm:p-6">
        <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div class="space-y-1">
            <p class="text-xs font-semibold uppercase tracking-[0.18em] text-primary">
              {{ kindLabels[selected.kind] }}
            </p>
            <h2 class="break-all text-lg font-semibold tracking-tight">{{ shortId(selected.id) }}</h2>
          </div>
          <Badge
            :variant="selected.status === 'open' ? 'destructive' : selected.status === 'resolved' ? 'secondary' : 'outline'"
          >
            {{ statusLabels[selected.status] }}
          </Badge>
        </div>

        <dl class="grid gap-4 sm:grid-cols-2">
          <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">提交用户</dt><dd>{{ selected.reporter_username }}</dd></div>
          <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">主体类型</dt><dd>{{ selected.subject_type }}</dd></div>
          <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">主体 ID</dt><dd><code class="break-all text-sm">{{ selected.candidate_id || selected.target_user_id || selected.risk_alert_id || "—" }}</code></dd></div>
          <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">期望动作</dt><dd><code class="break-all text-sm">{{ selected.requested_action || "—" }}</code></dd></div>
          <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">原因码</dt><dd><code class="break-all text-sm">{{ selected.reason_code }}</code></dd></div>
          <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">关联案件</dt><dd class="break-all">{{ selected.related_case_id || "—" }}</dd></div>
          <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">处理结果</dt><dd class="break-all">{{ selected.resolution_code || "—" }}</dd></div>
          <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">当前版本</dt><dd>{{ selected.version }}</dd></div>
          <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">当前负责人</dt><dd class="break-all">{{ selected.assigned_to_id || "未指派" }}</dd></div>
          <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">解决时间</dt><dd>{{ formatTime(selected.resolved_at) }}</dd></div>
          <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">SLA 截止</dt><dd>{{ formatTime(selected.sla_due_at) }}</dd></div>
          <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">自动升级</dt><dd>{{ selected.escalated_at ? `${formatTime(selected.escalated_at)}（${selected.escalation_count} 次）` : "未升级" }}</dd></div>
        </dl>

        <section class="space-y-2">
          <h3 class="font-semibold">用户说明</h3>
          <p class="whitespace-pre-wrap rounded-md bg-muted/50 p-4 text-sm leading-6">
            {{ selected.description || "未填写说明" }}
          </p>
        </section>
        <section v-if="selected.evidence_summary" class="space-y-2">
          <h3 class="font-semibold">证据摘要</h3>
          <p class="whitespace-pre-wrap rounded-md bg-muted/50 p-4 text-sm leading-6">
            {{ selected.evidence_summary }}
          </p>
        </section>
        <section v-if="selected.resolution_note" class="space-y-2">
          <h3 class="font-semibold">处理说明</h3>
          <p class="whitespace-pre-wrap rounded-md bg-muted/50 p-4 text-sm leading-6">
            {{ selected.resolution_note }}
          </p>
        </section>

        <section class="space-y-4 rounded-lg border bg-muted/30 p-4">
          <div class="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
            <Label class="grid gap-2">
              负责人用户 ID
              <Input v-model="assigneeId" maxlength="36" placeholder="审核员或管理员用户 ID" />
            </Label>
            <Button
              type="button"
              variant="outline"
              :disabled="busy || selected.status === 'resolved' || selected.status === 'dismissed' || !assigneeId.trim()"
              @click="assignSelectedCase"
            >
              {{ selected.assigned_to_id ? "转派负责人" : "指派负责人" }}
            </Button>
          </div>
          <Label class="grid gap-2">
            处理说明（不要粘贴密码、令牌或个人敏感信息）
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
            <Button
              v-if="selected.status === 'resolved' || selected.status === 'dismissed'"
              type="button"
              variant="outline"
              :disabled="busy"
              @click="reopenSelectedCase"
            >
              重新开启
            </Button>
          </div>
        </section>

        <section v-if="selected.notifications.length" class="space-y-3">
          <h3 class="font-semibold">结果通知</h3>
          <div class="space-y-2">
            <div
              v-for="notification in selected.notifications"
              :key="notification.id"
              class="flex flex-col gap-3 rounded-md border p-3 sm:flex-row sm:items-center sm:justify-between"
            >
              <div class="space-y-1 text-sm">
                <p class="font-medium">{{ notification.kind }} · {{ notification.status }}</p>
                <p class="text-muted-foreground">
                  尝试 {{ notification.attempts }} 次 · {{ formatTime(notification.sent_at || notification.failed_at || notification.available_at) }}
                </p>
                <p v-if="notification.last_error_code" class="text-destructive">
                  {{ notification.last_error_code }}
                </p>
              </div>
              <Button
                v-if="notification.status === 'failed'"
                type="button"
                variant="outline"
                :disabled="busy"
                @click="replayNotification(notification)"
              >
                重新发送
              </Button>
            </div>
          </div>
        </section>

        <section class="space-y-3">
          <h3 class="font-semibold">不可变处理时间线</h3>
          <ol class="space-y-3 border-l pl-5">
            <li v-for="event in selected.events" :key="event.id" class="space-y-1">
              <strong>{{ event.action }}</strong>
              <p class="text-sm">{{ event.previous_status || "创建" }} → {{ event.next_status }} · {{ event.reason_code }}</p>
              <p v-if="event.previous_assignee_id || event.next_assignee_id" class="text-sm text-muted-foreground">负责人：{{ event.previous_assignee_id || "未指派" }} → {{ event.next_assignee_id || "未指派" }}</p>
              <p v-if="event.note" class="whitespace-pre-wrap text-sm">{{ event.note }}</p>
              <small class="text-muted-foreground">{{ formatTime(event.created_at) }} · {{ event.request_id || "无请求号" }}</small>
            </li>
          </ol>
        </section>
      </article>
      <article v-else class="rounded-lg border bg-card p-8 text-center text-sm text-muted-foreground shadow-sm">
        请选择左侧案件查看详情。
      </article>
    </div>
  </section>
</template>
