<script setup lang="ts">
import {
  ApiError,
  type TrustCaseDetail,
  type TrustCaseKind,
  type TrustCaseResolutionCode,
  type TrustCaseStatus,
  type TrustCaseSummary,
} from "@password-detective/api-contract";
import { computed, onMounted, ref } from "vue";
import {
  createTrustCaseTransitionKey,
  getTrustCase,
  listTrustCases,
  transitionTrustCase,
} from "../services/trustCases";
import { useAdminAuthStore } from "../stores/auth";

const auth = useAdminAuthStore();
const cases = ref<TrustCaseSummary[]>([]);
const selected = ref<TrustCaseDetail | null>(null);
const kindFilter = ref<TrustCaseKind | "">("");
const statusFilter = ref<TrustCaseStatus | "">("open");
const query = ref("");
const total = ref(0);
const loading = ref(false);
const busy = ref(false);
const error = ref("");
const message = ref("");
const resolutionNote = ref("");

const kindLabels: Record<TrustCaseKind, string> = { report: "内容举报", appeal: "贡献申诉" };
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
    if (item.kind === "appeal") {
      result.push(
        { target: "resolved", code: "admin.appeal_upheld", label: "支持申诉" },
        { target: "resolved", code: "admin.appeal_denied", label: "驳回申诉", danger: true },
      );
    } else {
      result.push(
        { target: "resolved", code: "admin.action_taken", label: "确认并已处置" },
        { target: "resolved", code: "admin.no_violation", label: "确认无违规" },
      );
    }
    result.push({
      target: "dismissed",
      code: "admin.insufficient_evidence",
      label: "证据不足关闭",
      danger: true,
    });
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

async function loadCases(selectFirst = false): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const response = await listTrustCases(
      {
        kind: kindFilter.value,
        status: statusFilter.value,
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

async function openCase(caseId: string): Promise<void> {
  error.value = "";
  message.value = "";
  try {
    selected.value = await getTrustCase(caseId, token());
  } catch (value) {
    error.value = describeError(value);
  }
}

async function applyAction(action: (typeof actions.value)[number]): Promise<void> {
  if (!selected.value) return;
  const caseId = selected.value.id;
  busy.value = true;
  error.value = "";
  message.value = "";
  try {
    await transitionTrustCase(
      caseId,
      {
        target_status: action.target,
        resolution_code: action.code,
        resolution_note: resolutionNote.value.trim() || null,
      },
      token(),
      createTrustCaseTransitionKey(),
    );
    resolutionNote.value = "";
    message.value = `已完成“${action.label}”，处理事件已写入不可变时间线。`;
    await loadCases();
    await openCase(caseId);
  } catch (value) {
    error.value = describeError(value);
  } finally {
    busy.value = false;
  }
}

onMounted(() => loadCases(true));
</script>

<template>
  <section class="trust-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">M4 · COMMUNITY TRUST</p>
        <h1>举报与申诉</h1>
        <p>处理候选内容举报和贡献者申诉；自由文本只进入案件详情和事件时间线，不复制到审计摘要。</p>
      </div>
      <span class="badge">{{ total }} 个案件</span>
    </header>

    <form class="panel filters" @submit.prevent="loadCases(true)">
      <label>类型<select v-model="kindFilter"><option value="">全部</option><option value="report">举报</option><option value="appeal">申诉</option></select></label>
      <label>状态<select v-model="statusFilter"><option value="">全部</option><option value="open">待处理</option><option value="in_review">处理中</option><option value="resolved">已解决</option><option value="dismissed">已驳回</option></select></label>
      <label class="query">搜索<input v-model="query" maxlength="128" placeholder="案件 ID、候选 ID 或用户名" /></label>
      <button class="button" :disabled="loading">{{ loading ? "加载中…" : "筛选" }}</button>
    </form>

    <p v-if="error" class="alert error">{{ error }}</p>
    <p v-if="message" class="alert success">{{ message }}</p>

    <div class="case-layout">
      <aside class="panel case-list">
        <button
          v-for="item in cases"
          :key="item.id"
          class="case-row"
          :class="{ selected: selected?.id === item.id }"
          @click="openCase(item.id)"
        >
          <span><strong>{{ kindLabels[item.kind] }}</strong><span class="badge" :data-status="item.status">{{ statusLabels[item.status] }}</span></span>
          <code>{{ shortId(item.id) }}</code>
          <small>{{ item.reporter_username }} · {{ formatTime(item.created_at) }}</small>
          <small>候选 {{ shortId(item.candidate_id) }}</small>
        </button>
        <p v-if="!loading && cases.length === 0" class="empty">当前筛选条件下没有案件。</p>
      </aside>

      <article v-if="selected" class="panel detail">
        <div class="detail-title">
          <div><p class="eyebrow">{{ kindLabels[selected.kind] }}</p><h2>{{ shortId(selected.id) }}</h2></div>
          <span class="badge" :data-status="selected.status">{{ statusLabels[selected.status] }}</span>
        </div>
        <dl class="detail-grid">
          <div><dt>提交用户</dt><dd>{{ selected.reporter_username }}</dd></div>
          <div><dt>候选 ID</dt><dd><code>{{ selected.candidate_id }}</code></dd></div>
          <div><dt>原因码</dt><dd><code>{{ selected.reason_code }}</code></dd></div>
          <div><dt>关联案件</dt><dd>{{ selected.related_case_id || "—" }}</dd></div>
          <div><dt>处理结果</dt><dd>{{ selected.resolution_code || "—" }}</dd></div>
          <div><dt>解决时间</dt><dd>{{ formatTime(selected.resolved_at) }}</dd></div>
        </dl>
        <section><h3>用户说明</h3><p class="note">{{ selected.description || "未填写说明" }}</p></section>
        <section v-if="selected.resolution_note"><h3>处理说明</h3><p class="note">{{ selected.resolution_note }}</p></section>
        <section class="action-box">
          <label>处理说明（不要粘贴密码、令牌或个人敏感信息）<textarea v-model="resolutionNote" maxlength="1000" rows="3" /></label>
          <div class="actions"><button v-for="action in actions" :key="action.code" class="button" :class="{ danger: action.danger }" :disabled="busy" @click="applyAction(action)">{{ action.label }}</button></div>
        </section>
        <section><h3>不可变处理时间线</h3><ol class="timeline"><li v-for="event in selected.events" :key="event.id"><strong>{{ event.action }}</strong><p>{{ event.previous_status || "创建" }} → {{ event.next_status }} · {{ event.reason_code }}</p><p v-if="event.note">{{ event.note }}</p><small>{{ formatTime(event.created_at) }} · {{ event.request_id || "无请求号" }}</small></li></ol></section>
      </article>
      <article v-else class="panel empty">请选择左侧案件查看详情。</article>
    </div>
  </section>
</template>

<style scoped>
.trust-page { display: grid; gap: 18px; }
.page-heading, .detail-title, .case-row span, .actions { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
.page-heading h1, .detail-title h2 { margin: 4px 0; }
.page-heading p { margin: 0; color: var(--muted); }
.eyebrow { color: #2563eb !important; font-size: 12px; font-weight: 800; letter-spacing: .08em; }
.filters { display: flex; gap: 12px; align-items: end; flex-wrap: wrap; }
.filters label, .action-box label { display: grid; gap: 6px; color: var(--muted); font-size: 13px; font-weight: 700; }
.filters select, .filters input, textarea { box-sizing: border-box; width: 100%; padding: 11px 13px; border: 1px solid var(--border); border-radius: 10px; background: white; font: inherit; }
.filters .query { flex: 1; min-width: 250px; }
.case-layout { display: grid; grid-template-columns: minmax(280px, .7fr) minmax(0, 1.3fr); gap: 18px; align-items: start; }
.case-list { display: grid; gap: 10px; max-height: calc(100vh - 220px); overflow: auto; }
.case-row { display: grid; gap: 8px; padding: 14px; text-align: left; border: 1px solid var(--border); border-radius: 12px; background: white; cursor: pointer; }
.case-row.selected, .case-row:hover { border-color: #60a5fa; background: #eff6ff; }
.case-row code, .case-row small { color: var(--muted); overflow-wrap: anywhere; }
.badge { padding: 4px 9px; border-radius: 999px; background: #e2e8f0; font-size: 12px; font-weight: 800; }
.badge[data-status="open"] { background: #fff7ed; color: #9a3412; }.badge[data-status="in_review"] { background: #eff6ff; color: #1d4ed8; }.badge[data-status="resolved"] { background: #ecfdf3; color: #067647; }.badge[data-status="dismissed"] { background: #f1f5f9; color: #475569; }
.detail { display: grid; gap: 18px; }.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 0; }.detail-grid dt { color: var(--muted); font-size: 12px; font-weight: 700; }.detail-grid dd { margin: 4px 0 0; overflow-wrap: anywhere; }
.note { padding: 13px; border-radius: 10px; background: #f8fafc; white-space: pre-wrap; }.action-box { display: grid; gap: 12px; padding: 15px; border-radius: 12px; background: #f8fafc; }.actions { justify-content: flex-start; flex-wrap: wrap; }.button.danger { background: #b42318; }.timeline { display: grid; gap: 12px; padding-left: 20px; }.timeline li { padding-left: 8px; }.timeline p { margin: 5px 0; }.timeline small, .empty { color: var(--muted); }
@media (max-width: 900px) { .case-layout { grid-template-columns: 1fr; }.case-list { max-height: none; } } @media (max-width: 600px) { .detail-grid { grid-template-columns: 1fr; } }
</style>
