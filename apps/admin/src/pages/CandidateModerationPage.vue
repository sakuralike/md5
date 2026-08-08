<script setup lang="ts">
import type {
  CandidateModerationDetail,
  CandidateModerationSummary,
  CandidateStatus,
  ManualTransitionReason,
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
import { ApiError } from "@password-detective/api-contract";
import {
  createTransitionKey,
  getModerationCandidate,
  listModerationCandidates,
  transitionModerationCandidate,
} from "../services/candidateModeration";
import { useAdminAuthStore } from "../stores/auth";

const auth = useAdminAuthStore();
const candidates = ref<CandidateModerationSummary[]>([]);
const selected = ref<CandidateModerationDetail | null>(null);
const statusFilter = ref<CandidateStatus | "all">("all");
const query = ref("");
const total = ref(0);
const loading = ref(false);
const detailLoading = ref(false);
const activeAction = ref("");
const message = ref("");
const error = ref("");
const reasonNote = ref("");

const statusLabels: Record<CandidateStatus, string> = {
  pending: "待验证",
  verified: "已验证",
  rejected: "已拒绝",
  quarantined: "隔离中",
};

const sourceLabels = {
  automatic: "自动规则",
  manual: "人工处置",
};

const adjustmentDirectionLabels = {
  invalidate: "扣回奖励",
  restore: "恢复奖励",
};

const rewardKindLabels = {
  contribution: "贡献奖励",
  verification: "验证奖励",
};

const correlationSignalLabels = {
  installation: "共享安装实例",
  ip_prefix: "共享 IP 网段",
};

const availableActions = computed(() => {
  if (!selected.value) return [];
  const actions: Array<{ target: CandidateStatus; reason: ManualTransitionReason; label: string; danger?: boolean }> = [];
  switch (selected.value.status) {
    case "pending":
      actions.push(
        { target: "verified", reason: "manual.verified_by_review", label: "审核通过" },
        { target: "quarantined", reason: "manual.evidence_conflict", label: "隔离候选" },
        { target: "rejected", reason: "manual.invalid_candidate", label: "拒绝候选", danger: true },
      );
      break;
    case "verified":
      actions.push(
        { target: "quarantined", reason: "manual.security_hold", label: "安全隔离" },
        { target: "rejected", reason: "manual.policy_violation", label: "撤销并拒绝", danger: true },
      );
      break;
    case "quarantined":
      actions.push(
        { target: "pending", reason: "manual.quarantine_cleared", label: "解除隔离并复审" },
        { target: "verified", reason: "manual.quarantine_cleared", label: "解除隔离并通过" },
        { target: "rejected", reason: "manual.invalid_candidate", label: "隔离后拒绝", danger: true },
      );
      break;
    case "rejected":
      actions.push({ target: "pending", reason: "manual.review_reopened", label: "重新开启审核" });
      break;
  }
  return actions;
});

function requireToken(): string {
  if (!auth.accessToken) throw new Error("管理会话已失效，请重新登录");
  return auth.accessToken;
}

function formatTime(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function shortId(value: string): string {
  return value.length > 18 ? `${value.slice(0, 8)}…${value.slice(-6)}` : value;
}

function signedAmount(value: number): string {
  return value > 0 ? `+${value}` : String(value);
}

function weightReduction(raw: number, effective: number): string {
  return Math.max(raw - effective, 0).toFixed(3);
}

function statusVariant(status: CandidateStatus): "default" | "secondary" | "destructive" | "outline" {
  if (status === "verified") return "secondary";
  if (status === "rejected") return "destructive";
  return status === "quarantined" ? "default" : "outline";
}

function describeError(value: unknown): string {
  return value instanceof ApiError ? `${value.body.message}（${value.body.code}）` : value instanceof Error ? value.message : "操作失败";
}

async function loadCandidates(selectFirst = false): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const response = await listModerationCandidates(
      { status: statusFilter.value === "all" ? "" : statusFilter.value, query: query.value, page: 1, pageSize: 50 },
      requireToken(),
    );
    candidates.value = response.items;
    total.value = response.total;
    if (selectFirst && response.items.length > 0) await openCandidate(response.items[0].id);
    if (selected.value && !response.items.some((item) => item.id === selected.value?.id)) selected.value = null;
  } catch (value) {
    error.value = describeError(value);
  } finally {
    loading.value = false;
  }
}

async function openCandidate(candidateId: string): Promise<void> {
  detailLoading.value = true;
  error.value = "";
  message.value = "";
  try {
    selected.value = await getModerationCandidate(candidateId, requireToken());
  } catch (value) {
    error.value = describeError(value);
  } finally {
    detailLoading.value = false;
  }
}

async function applyTransition(action: { target: CandidateStatus; reason: ManualTransitionReason; label: string }): Promise<void> {
  if (!selected.value) return;
  activeAction.value = action.target;
  error.value = "";
  message.value = "";
  const candidateId = selected.value.id;
  try {
    const response = await transitionModerationCandidate(
      candidateId,
      { target_status: action.target, reason_code: action.reason, reason_note: reasonNote.value.trim() || null },
      requireToken(),
      createTransitionKey(),
    );
    reasonNote.value = "";
    await Promise.all([loadCandidates(), openCandidate(candidateId)]);
    const adjustment = response.reward_adjustment;
    const adjustmentText = adjustment.direction
      ? `奖励调整：积分 ${signedAmount(adjustment.points_amount)}，信誉 ${signedAmount(adjustment.reputation_amount)}，影响 ${adjustment.affected_users} 个账号。`
      : "本次状态变更无需奖励调整。";
    message.value = `已完成“${action.label}”，不可变状态时间线和审计日志已写入。${adjustmentText}`;
  } catch (value) {
    error.value = describeError(value);
  } finally {
    activeAction.value = "";
  }
}

onMounted(() => loadCandidates(true));
</script>

<template>
  <section class="space-y-5">
    <header class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div class="space-y-2">
        <p class="text-xs font-semibold uppercase tracking-[0.18em] text-primary">
          M4 · 人工审核闭环
        </p>
        <h1 class="text-2xl font-semibold tracking-tight">候选审核</h1>
        <p class="max-w-3xl text-sm leading-6 text-muted-foreground">
          按状态或指纹定位候选，查看独立证据与状态时间线，并执行具备 MFA、幂等和审计约束的人工处置。
        </p>
      </div>
      <aside class="max-w-md space-y-2 rounded-lg border border-primary/30 bg-primary/10 p-4 text-sm">
        <strong class="text-primary">最小披露</strong>
        <p class="leading-6 text-muted-foreground">
          管理端只展示候选 ID、存档指纹和证据摘要，不读取或返回候选密码材料。
        </p>
      </aside>
    </header>

    <form
      class="grid gap-4 rounded-lg border bg-card p-4 text-card-foreground shadow-sm md:grid-cols-[minmax(10rem,0.7fr)_minmax(16rem,1.5fr)_auto_auto] md:items-end"
      aria-label="候选筛选"
      @submit.prevent="loadCandidates(true)"
    >
      <Label class="grid gap-2">
        状态
        <Select v-model="statusFilter">
          <SelectTrigger><SelectValue placeholder="全部状态" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部状态</SelectItem>
            <SelectItem value="pending">待验证</SelectItem>
            <SelectItem value="verified">已验证</SelectItem>
            <SelectItem value="rejected">已拒绝</SelectItem>
            <SelectItem value="quarantined">隔离中</SelectItem>
          </SelectContent>
        </Select>
      </Label>
      <Label class="grid gap-2">
        候选 / 存档 / 指纹
        <Input v-model="query" placeholder="输入 ID 或哈希片段" />
      </Label>
      <Button type="submit" :disabled="loading">
        {{ loading ? "查询中…" : "查询" }}
      </Button>
      <Badge variant="secondary" class="justify-center md:mb-2">共 {{ total }} 条</Badge>
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

    <section class="grid items-start gap-5 lg:grid-cols-[minmax(18.75rem,0.72fr)_minmax(0,1.28fr)]">
      <aside class="grid max-h-[calc(100vh-14rem)] gap-3 overflow-y-auto rounded-lg border bg-card p-4 shadow-sm lg:sticky lg:top-4">
        <div class="flex items-start justify-between gap-3">
          <h2 class="font-semibold">审核队列</h2>
          <span class="text-xs text-muted-foreground">当前页 {{ candidates.length }} 条</span>
        </div>
        <p v-if="!loading && candidates.length === 0" class="py-8 text-center text-sm text-muted-foreground">
          没有符合条件的候选记录。
        </p>
        <Button
          v-for="candidate in candidates"
          :key="candidate.id"
          type="button"
          variant="outline"
          class="h-auto w-full justify-start whitespace-normal p-4 text-left"
          :class="selected?.id === candidate.id ? 'border-primary/60 bg-primary/10' : ''"
          @click="openCandidate(candidate.id)"
        >
          <span class="grid w-full gap-2">
            <span class="flex items-start justify-between gap-3">
              <strong class="break-all">{{ shortId(candidate.id) }}</strong>
              <Badge :variant="statusVariant(candidate.status)">
                {{ statusLabels[candidate.status] }}
              </Badge>
            </span>
            <code class="break-all text-xs text-muted-foreground">
              {{ candidate.fingerprints[0]?.algorithm }}:{{ candidate.fingerprints[0]?.digest }}
            </code>
            <small class="flex flex-wrap gap-x-3 gap-y-1 text-muted-foreground">
              <span>提交 {{ candidate.submission_count }}</span>
              <span>反馈 {{ candidate.feedback_count }}</span>
              <span>{{ formatTime(candidate.updated_at) }}</span>
            </small>
          </span>
        </Button>
      </aside>

      <div class="space-y-5">
        <section v-if="detailLoading" class="rounded-lg border bg-card p-8 text-center text-sm text-muted-foreground shadow-sm">
          正在加载审核详情…
        </section>
        <template v-else-if="selected">
          <section class="space-y-5 rounded-lg border bg-card p-5 text-card-foreground shadow-sm sm:p-6">
            <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div class="space-y-1">
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-primary">候选详情</p>
                <h2 class="break-all text-lg font-semibold tracking-tight">{{ shortId(selected.id) }}</h2>
              </div>
              <Badge :variant="statusVariant(selected.status)">{{ statusLabels[selected.status] }}</Badge>
            </div>
            <dl class="grid gap-4 sm:grid-cols-2">
              <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">存档 ID</dt><dd><code class="break-all text-sm">{{ selected.archive_id }}</code></dd></div>
              <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">置信度</dt><dd>{{ selected.confidence_score.toFixed(3) }}</dd></div>
              <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">独立成功证据</dt><dd>{{ selected.evidence_snapshot.independent_success_count }} / 权重 {{ selected.evidence_snapshot.success_weight }}</dd></div>
              <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">独立失败证据</dt><dd>{{ selected.evidence_snapshot.independent_failure_count }} / 权重 {{ selected.evidence_snapshot.failure_weight }}</dd></div>
            </dl>
            <div class="grid gap-2">
              <strong class="text-sm">存档指纹</strong>
              <code
                v-for="fingerprint in selected.fingerprints"
                :key="`${fingerprint.algorithm}:${fingerprint.digest}`"
                class="break-all rounded-md bg-muted px-3 py-2 text-xs"
              >
                {{ fingerprint.algorithm }}:{{ fingerprint.digest }}
              </code>
            </div>
          </section>

          <section class="space-y-5 rounded-lg border border-primary/20 bg-card p-5 text-card-foreground shadow-sm sm:p-6">
            <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div class="space-y-1">
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-primary">
                  {{ selected.correlation_snapshot.rule_version }}
                </p>
                <h2 class="text-lg font-semibold tracking-tight">关联证据与动态降权</h2>
              </div>
              <Badge :variant="selected.correlation_snapshot.correlated_group_count > 0 ? 'default' : 'outline'">
                {{ selected.correlation_snapshot.correlated_group_count }} 个关联组
              </Badge>
            </div>
            <p class="text-sm leading-6 text-muted-foreground">
              关联键只在后端内存中参与计算；此处仅展示账号、证据 ID 和关联类型，不返回 IP 网段或安装标识哈希。
            </p>
            <dl class="grid gap-4 sm:grid-cols-2">
              <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">反馈 / 独立组</dt><dd>{{ selected.correlation_snapshot.feedback_count }} / {{ selected.correlation_snapshot.independent_group_count }}</dd></div>
              <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">被降权反馈</dt><dd>{{ selected.correlation_snapshot.downweighted_feedback_count }}</dd></div>
              <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">成功权重</dt><dd>{{ selected.correlation_snapshot.raw_success_weight }} → {{ selected.correlation_snapshot.effective_success_weight }}（降低 {{ weightReduction(selected.correlation_snapshot.raw_success_weight, selected.correlation_snapshot.effective_success_weight) }}）</dd></div>
              <div class="space-y-1"><dt class="text-xs font-semibold text-muted-foreground">失败权重</dt><dd>{{ selected.correlation_snapshot.raw_failure_weight }} → {{ selected.correlation_snapshot.effective_failure_weight }}（降低 {{ weightReduction(selected.correlation_snapshot.raw_failure_weight, selected.correlation_snapshot.effective_failure_weight) }}）</dd></div>
            </dl>
            <p
              v-if="selected.correlation_snapshot.correlated_group_count === 0"
              class="rounded-md bg-muted px-4 py-6 text-center text-sm text-muted-foreground"
            >
              当前未发现共享安装实例或 IP 网段形成的关联反馈组。
            </p>
            <ol v-else class="space-y-3">
              <li
                v-for="group in selected.correlation_groups.filter((item) => item.member_count > 1)"
                :key="group.group_id"
                class="space-y-2 rounded-lg border bg-background p-4"
              >
                <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <strong>{{ group.group_id }} · {{ group.member_count }} 个账号</strong>
                  <Badge variant="outline">
                    {{ group.shared_signals.map((signal) => correlationSignalLabels[signal]).join(" + ") }}
                  </Badge>
                </div>
                <p class="text-sm leading-6">成功 {{ group.success_count }} 条，权重 {{ group.raw_success_weight }} → {{ group.effective_success_weight }}；失败 {{ group.failure_count }} 条，权重 {{ group.raw_failure_weight }} → {{ group.effective_failure_weight }}</p>
                <small class="block break-all text-muted-foreground">账号：{{ group.user_ids.map(shortId).join("、") }} · 证据：{{ group.feedback_ids.map(shortId).join("、") }}</small>
              </li>
            </ol>
            <details v-if="selected.correlation_assessments.length > 0" class="rounded-lg border bg-muted/30 p-4">
              <summary class="cursor-pointer font-semibold text-primary">
                查看不可变评估历史（{{ selected.correlation_assessments.length }} 条）
              </summary>
              <ol class="mt-4 space-y-3 border-l pl-5">
                <li v-for="assessment in selected.correlation_assessments.slice(0, 20)" :key="assessment.id" class="space-y-1">
                  <strong>{{ assessment.correlated_group_count }} 个关联组 · {{ assessment.downweighted_feedback_count }} 条降权</strong>
                  <p class="text-sm">成功 {{ assessment.raw_success_weight }} → {{ assessment.effective_success_weight }}；失败 {{ assessment.raw_failure_weight }} → {{ assessment.effective_failure_weight }}</p>
                  <small class="text-muted-foreground">{{ formatTime(assessment.created_at) }} · 触发证据 {{ shortId(assessment.trigger_evidence_id) }}</small>
                </li>
              </ol>
            </details>
          </section>

          <section class="space-y-4 rounded-lg border bg-card p-5 text-card-foreground shadow-sm sm:p-6">
            <div class="space-y-1">
              <p class="text-xs font-semibold uppercase tracking-[0.18em] text-primary">受控处置</p>
              <h2 class="text-lg font-semibold tracking-tight">状态操作</h2>
            </div>
            <Label class="grid gap-2">
              审核说明（进入状态时间线，不写入审计详情）
              <Textarea
                v-model="reasonNote"
                rows="3"
                maxlength="500"
                placeholder="使用合成、非敏感说明；禁止粘贴密码、令牌或个人信息。"
              />
            </Label>
            <div class="flex flex-wrap gap-2">
              <Button
                v-for="action in availableActions"
                :key="`${action.target}:${action.reason}`"
                type="button"
                :variant="action.danger ? 'destructive' : 'default'"
                :disabled="Boolean(activeAction)"
                @click="applyTransition(action)"
              >
                {{ activeAction === action.target ? "处理中…" : action.label }}
              </Button>
            </div>
          </section>

          <section class="space-y-4 rounded-lg border bg-card p-5 text-card-foreground shadow-sm sm:p-6">
            <div class="flex items-start justify-between gap-3">
              <h2 class="text-lg font-semibold tracking-tight">状态时间线</h2>
              <Badge variant="secondary">{{ selected.state_events.length }} 条</Badge>
            </div>
            <p v-if="selected.state_events.length === 0" class="py-6 text-center text-sm text-muted-foreground">
              尚无状态变更事件。
            </p>
            <ol v-else class="space-y-3 border-l pl-5">
              <li v-for="event in selected.state_events" :key="event.id" class="space-y-2">
                <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <strong>{{ statusLabels[event.previous_status] }} → {{ statusLabels[event.next_status] }}</strong>
                  <Badge variant="outline">{{ sourceLabels[event.transition_source] }}</Badge>
                </div>
                <p class="break-all text-sm">{{ event.reason_code }}<span v-if="event.reason_note"> · {{ event.reason_note }}</span></p>
                <small class="text-muted-foreground">{{ formatTime(event.created_at) }} · 规则 {{ event.rule_version }}<span v-if="event.actor_id"> · 操作人 {{ shortId(event.actor_id) }}</span></small>
              </li>
            </ol>
          </section>

          <section class="space-y-4 rounded-lg border bg-card p-5 text-card-foreground shadow-sm sm:p-6">
            <div class="flex items-start justify-between gap-3">
              <h2 class="text-lg font-semibold tracking-tight">积分 / 信誉调整</h2>
              <Badge variant="secondary">{{ selected.reward_adjustments.length }} 条</Badge>
            </div>
            <p v-if="selected.reward_adjustments.length === 0" class="py-6 text-center text-sm text-muted-foreground">
              尚无奖励扣回或恢复事件。
            </p>
            <ol v-else class="space-y-3 border-l pl-5">
              <li v-for="event in selected.reward_adjustments" :key="event.id" class="space-y-2">
                <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <strong>{{ adjustmentDirectionLabels[event.direction] }} · {{ rewardKindLabels[event.reward_kind] }}</strong>
                  <Badge variant="outline">{{ shortId(event.user_id) }}</Badge>
                </div>
                <p class="text-sm">积分 {{ signedAmount(event.points_amount) }} · 信誉 {{ signedAmount(event.reputation_amount) }}</p>
                <small class="text-muted-foreground">{{ formatTime(event.created_at) }} · {{ event.rule_version }} · 状态事件 {{ shortId(event.state_event_id) }}</small>
              </li>
            </ol>
          </section>

          <section class="space-y-4 rounded-lg border bg-card p-5 text-card-foreground shadow-sm sm:p-6">
            <div class="flex items-start justify-between gap-3">
              <h2 class="text-lg font-semibold tracking-tight">证据修订</h2>
              <Badge variant="secondary">{{ selected.evidence_events.length }} 条</Badge>
            </div>
            <p v-if="selected.evidence_events.length === 0" class="py-6 text-center text-sm text-muted-foreground">
              尚无验证证据。
            </p>
            <ol v-else class="space-y-3 border-l pl-5">
              <li v-for="event in selected.evidence_events" :key="event.id" class="space-y-2">
                <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <strong>{{ event.outcome === "success" ? "成功" : "失败" }} · 权重 {{ event.weight }}</strong>
                  <Badge variant="outline">{{ event.source }}</Badge>
                </div>
                <p class="text-sm">修订 {{ event.revision }} · 账号 {{ shortId(event.user_id) }}</p>
                <small class="text-muted-foreground">{{ formatTime(event.created_at) }} · {{ event.rule_version }}</small>
              </li>
            </ol>
          </section>
        </template>
        <section v-else class="rounded-lg border bg-card p-8 text-center text-sm text-muted-foreground shadow-sm">
          从左侧审核队列选择一条候选记录。
        </section>
      </div>
    </section>
  </section>
</template>
