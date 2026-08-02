<script setup lang="ts">
import type {
  CandidateModerationDetail,
  CandidateModerationSummary,
  CandidateStatus,
  ManualTransitionReason,
} from "@password-detective/api-contract";
import { computed, onMounted, ref } from "vue";
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
const statusFilter = ref<CandidateStatus | "">("");
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

function describeError(value: unknown): string {
  return value instanceof ApiError ? `${value.body.message}（${value.body.code}）` : value instanceof Error ? value.message : "操作失败";
}

async function loadCandidates(selectFirst = false): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const response = await listModerationCandidates(
      { status: statusFilter.value, query: query.value, page: 1, pageSize: 50 },
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
  <section class="stack">
    <header class="panel moderation-heading">
      <div>
        <div class="eyebrow">M4 · 人工审核闭环</div>
        <h1>候选审核</h1>
        <p class="lead">按状态或指纹定位候选，查看独立证据与状态时间线，并执行具备 MFA、幂等和审计约束的人工处置。</p>
      </div>
      <aside class="safety-note">
        <strong>最小披露</strong>
        <span>管理端只展示候选 ID、存档指纹和证据摘要，不读取或返回候选密码材料。</span>
      </aside>
    </header>

    <section class="panel filter-bar" aria-label="候选筛选">
      <label class="field"><span>状态</span><select v-model="statusFilter"><option value="">全部状态</option><option v-for="(label, value) in statusLabels" :key="value" :value="value">{{ label }}</option></select></label>
      <label class="field query-field"><span>候选 / 存档 / 指纹</span><input v-model="query" placeholder="输入 ID 或哈希片段" @keyup.enter="loadCandidates()" /></label>
      <button class="button" type="button" :disabled="loading" @click="loadCandidates()">{{ loading ? "查询中…" : "查询" }}</button>
      <span class="muted">共 {{ total }} 条</span>
    </section>

    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="message" class="success" role="status">{{ message }}</p>

    <section class="moderation-layout">
      <div class="panel candidate-list-panel">
        <div class="section-title"><h2>审核队列</h2><span class="muted">当前页 {{ candidates.length }} 条</span></div>
        <div v-if="!loading && candidates.length === 0" class="empty-state">没有符合条件的候选记录。</div>
        <button v-for="candidate in candidates" :key="candidate.id" type="button" class="candidate-row" :class="{ selected: selected?.id === candidate.id }" @click="openCandidate(candidate.id)">
          <div class="row-heading"><strong>{{ shortId(candidate.id) }}</strong><span class="badge status-badge" :data-status="candidate.status">{{ statusLabels[candidate.status] }}</span></div>
          <code>{{ candidate.fingerprints[0]?.algorithm }}:{{ candidate.fingerprints[0]?.digest }}</code>
          <div class="row-meta"><span>提交 {{ candidate.submission_count }}</span><span>反馈 {{ candidate.feedback_count }}</span><span>{{ formatTime(candidate.updated_at) }}</span></div>
        </button>
      </div>

      <div class="stack detail-stack">
        <section v-if="detailLoading" class="panel empty-state">正在加载审核详情…</section>
        <template v-else-if="selected">
          <section class="panel stack">
            <div class="section-title"><div><div class="eyebrow">候选详情</div><h2>{{ shortId(selected.id) }}</h2></div><span class="badge status-badge" :data-status="selected.status">{{ statusLabels[selected.status] }}</span></div>
            <dl class="detail-grid">
              <div><dt>存档 ID</dt><dd><code>{{ selected.archive_id }}</code></dd></div>
              <div><dt>置信度</dt><dd>{{ selected.confidence_score.toFixed(3) }}</dd></div>
              <div><dt>独立成功证据</dt><dd>{{ selected.evidence_snapshot.independent_success_count }} / 权重 {{ selected.evidence_snapshot.success_weight }}</dd></div>
              <div><dt>独立失败证据</dt><dd>{{ selected.evidence_snapshot.independent_failure_count }} / 权重 {{ selected.evidence_snapshot.failure_weight }}</dd></div>
            </dl>
            <div class="fingerprints"><strong>存档指纹</strong><code v-for="fingerprint in selected.fingerprints" :key="`${fingerprint.algorithm}:${fingerprint.digest}`">{{ fingerprint.algorithm }}:{{ fingerprint.digest }}</code></div>
          </section>

          <section class="panel stack">
            <div><div class="eyebrow">受控处置</div><h2>状态操作</h2></div>
            <label class="field"><span>审核说明（进入状态时间线，不写入审计详情）</span><textarea v-model="reasonNote" rows="3" maxlength="500" placeholder="使用合成、非敏感说明；禁止粘贴密码、令牌或个人信息。"></textarea></label>
            <div class="actions"><button v-for="action in availableActions" :key="`${action.target}:${action.reason}`" class="button" :class="{ danger: action.danger }" type="button" :disabled="Boolean(activeAction)" @click="applyTransition(action)">{{ activeAction === action.target ? "处理中…" : action.label }}</button></div>
          </section>

          <section class="panel stack">
            <div class="section-title"><h2>状态时间线</h2><span class="muted">{{ selected.state_events.length }} 条</span></div>
            <div v-if="selected.state_events.length === 0" class="empty-state">尚无状态变更事件。</div>
            <ol v-else class="timeline">
              <li v-for="event in selected.state_events" :key="event.id">
                <div class="timeline-title"><strong>{{ statusLabels[event.previous_status] }} → {{ statusLabels[event.next_status] }}</strong><span class="badge">{{ sourceLabels[event.transition_source] }}</span></div>
                <p>{{ event.reason_code }}<span v-if="event.reason_note"> · {{ event.reason_note }}</span></p>
                <small>{{ formatTime(event.created_at) }} · 规则 {{ event.rule_version }}<span v-if="event.actor_id"> · 操作人 {{ shortId(event.actor_id) }}</span></small>
              </li>
            </ol>
          </section>

          <section class="panel stack">
            <div class="section-title"><h2>积分 / 信誉调整</h2><span class="muted">{{ selected.reward_adjustments.length }} 条</span></div>
            <div v-if="selected.reward_adjustments.length === 0" class="empty-state">尚无奖励扣回或恢复事件。</div>
            <ol v-else class="timeline reward-timeline">
              <li v-for="event in selected.reward_adjustments" :key="event.id">
                <div class="timeline-title"><strong>{{ adjustmentDirectionLabels[event.direction] }} · {{ rewardKindLabels[event.reward_kind] }}</strong><span class="badge">{{ shortId(event.user_id) }}</span></div>
                <p>积分 {{ signedAmount(event.points_amount) }} · 信誉 {{ signedAmount(event.reputation_amount) }}</p>
                <small>{{ formatTime(event.created_at) }} · {{ event.rule_version }} · 状态事件 {{ shortId(event.state_event_id) }}</small>
              </li>
            </ol>
          </section>

          <section class="panel stack">
            <div class="section-title"><h2>证据修订</h2><span class="muted">{{ selected.evidence_events.length }} 条</span></div>
            <div v-if="selected.evidence_events.length === 0" class="empty-state">尚无验证证据。</div>
            <ol v-else class="timeline evidence-timeline"><li v-for="event in selected.evidence_events" :key="event.id"><div class="timeline-title"><strong>{{ event.outcome === "success" ? "成功" : "失败" }} · 权重 {{ event.weight }}</strong><span class="badge">{{ event.source }}</span></div><p>修订 {{ event.revision }} · 账号 {{ shortId(event.user_id) }}</p><small>{{ formatTime(event.created_at) }} · {{ event.rule_version }}</small></li></ol>
          </section>
        </template>
        <section v-else class="panel empty-state">从左侧审核队列选择一条候选记录。</section>
      </div>
    </section>
  </section>
</template>

<style scoped>
.moderation-heading { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(260px, .65fr); gap: 24px; align-items: center; }
.safety-note { display: grid; gap: 8px; padding: 18px; border: 1px solid #bae6fd; border-radius: 14px; color: #0c4a6e; background: #f0f9ff; }
.filter-bar { display: flex; gap: 14px; align-items: end; flex-wrap: wrap; }
.filter-bar .field { min-width: 150px; }
.query-field { flex: 1; min-width: 260px !important; }
.moderation-layout { display: grid; grid-template-columns: minmax(300px, .72fr) minmax(0, 1.28fr); gap: 20px; align-items: start; }
.candidate-list-panel { display: grid; gap: 10px; position: sticky; top: 16px; max-height: calc(100vh - 32px); overflow: auto; }
.section-title, .row-heading, .timeline-title { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.candidate-row { display: grid; gap: 9px; width: 100%; padding: 16px; text-align: left; border: 1px solid var(--border); border-radius: 14px; background: #fff; cursor: pointer; }
.candidate-row:hover, .candidate-row.selected { border-color: #60a5fa; background: #f0f7ff; }
.candidate-row code { overflow-wrap: anywhere; font-size: 11px; color: var(--muted); }
.row-meta { display: flex; gap: 12px; flex-wrap: wrap; color: var(--muted); font-size: 12px; }
.status-badge[data-status="verified"] { color: #067647; background: #ecfdf3; }
.status-badge[data-status="rejected"] { color: #b42318; background: #fff1f0; }
.status-badge[data-status="quarantined"] { color: #9a3412; background: #fff7ed; }
.detail-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin: 0; }
.detail-grid dt { color: var(--muted); font-size: 12px; font-weight: 700; }
.detail-grid dd { margin: 5px 0 0; overflow-wrap: anywhere; }
.fingerprints { display: grid; gap: 8px; }
.fingerprints code { overflow-wrap: anywhere; padding: 10px; border-radius: 10px; background: #f8fafc; font-size: 12px; }
.timeline { display: grid; gap: 14px; margin: 0; padding: 0; list-style: none; }
.timeline li { padding: 14px 0 14px 18px; border-left: 3px solid #bfdbfe; }
.timeline p { margin: 7px 0; overflow-wrap: anywhere; }
.timeline small { color: var(--muted); }
.field textarea, .field select { box-sizing: border-box; width: 100%; border: 1px solid var(--border); border-radius: 11px; padding: 12px 14px; background: white; font: inherit; }
.empty-state { padding: 28px; text-align: center; color: var(--muted); }
@media (max-width: 960px) { .moderation-heading, .moderation-layout { grid-template-columns: 1fr; } .candidate-list-panel { position: static; max-height: none; } }
@media (max-width: 640px) { .detail-grid { grid-template-columns: 1fr; } .filter-bar { align-items: stretch; } .filter-bar .field, .query-field { min-width: 100% !important; } }
</style>
