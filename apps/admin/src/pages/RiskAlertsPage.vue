<script setup lang="ts">
import {
  ApiError,
  type RiskAlertDetail,
  type RiskAlertNotificationKind,
  type RiskAlertNotificationStatus,
  type RiskAlertOperator,
  type RiskAlertResolutionCode,
  type RiskAlertSlaState,
  type RiskAlertStatus,
  type RiskAlertSummary,
} from "@password-detective/api-contract";
import { computed, onMounted, ref } from "vue";
import {
  assignRiskAlert,
  createRiskAlertAssignmentKey,
  createRiskAlertTransitionKey,
  getRiskAlert,
  listRiskAlertOperators,
  listRiskAlerts,
  transitionRiskAlert,
} from "../services/riskAlerts";
import { useAdminAuthStore } from "../stores/auth";

const auth = useAdminAuthStore();
const alerts = ref<RiskAlertSummary[]>([]);
const operators = ref<RiskAlertOperator[]>([]);
const selected = ref<RiskAlertDetail | null>(null);
const statusFilter = ref<RiskAlertStatus | "">("open");
const assigneeFilter = ref("");
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

function operatorName(operatorId: string | null): string {
  if (!operatorId) return "未指派";
  return operators.value.find((operator) => operator.id === operatorId)?.username ?? shortId(operatorId);
}

async function loadOperators(): Promise<void> {
  operators.value = await listRiskAlertOperators(token());
}

async function loadAlerts(selectFirst = false): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const response = await listRiskAlerts(
      {
        kind: "failure_surge",
        severity: "high",
        status: statusFilter.value,
        assignedToId: assigneeFilter.value,
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
    message.value = "告警负责人已更新，指派事件与通知已进入闭环。";
    await loadAlerts();
    await openAlert(alertId);
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
    message.value = `已完成“${action.label}”，处置事件已写入不可变时间线。`;
    await loadAlerts();
    await openAlert(alertId);
  } catch (value) {
    error.value = describeError(value);
  } finally {
    busy.value = false;
  }
}

onMounted(async () => {
  try {
    await loadOperators();
    await loadAlerts(true);
  } catch (value) {
    error.value = describeError(value);
  }
});
</script>

<template>
  <section class="risk-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">M4 · RISK OPERATIONS</p>
        <h1>风险告警</h1>
        <p>按版本化 SLA 完成检测、指派、响应、解决和通知闭环；页面只展示最小化聚合证据。</p>
      </div>
      <strong>{{ total }} 条</strong>
    </header>

    <form class="panel filters" @submit.prevent="loadAlerts(true)">
      <label>状态<select v-model="statusFilter"><option value="">全部</option><option value="open">待响应</option><option value="acknowledged">核查中</option><option value="resolved">已解决</option></select></label>
      <label>负责人<select v-model="assigneeFilter"><option value="">全部</option><option v-for="operator in operators" :key="operator.id" :value="operator.id">{{ operator.username }}</option></select></label>
      <label class="check"><input v-model="overdueOnly" type="checkbox" />仅看超时</label>
      <label class="query">候选或告警 ID<input v-model="query" maxlength="128" placeholder="输入合成候选 ID" /></label>
      <button class="button" :disabled="loading">{{ loading ? "加载中…" : "筛选" }}</button>
    </form>

    <p v-if="error" class="notice error">{{ error }}</p>
    <p v-if="message" class="notice success">{{ message }}</p>

    <div class="risk-layout">
      <aside class="panel alert-list">
        <button v-for="alert in alerts" :key="alert.id" class="alert-row" :class="{ selected: selected?.id === alert.id }" @click="openAlert(alert.id)">
          <span><strong>{{ statusLabels[alert.status] }}</strong><span class="badge" :data-sla="alert.sla_state">{{ slaLabels[alert.sla_state] }}</span></span>
          <code>{{ shortId(alert.candidate_id) }}</code>
          <small>{{ alert.independent_failure_count }} 个独立失败 · {{ operatorName(alert.assigned_to_id) }}</small>
          <small>响应截止 {{ formatTime(alert.acknowledge_due_at) }}</small>
        </button>
        <p v-if="!loading && alerts.length === 0" class="empty">当前筛选条件下没有风险告警。</p>
      </aside>

      <article v-if="selected" class="panel detail">
        <div class="detail-title">
          <div><p class="eyebrow">HIGH · FAILURE SURGE</p><h2>{{ shortId(selected.id) }}</h2></div>
          <div class="badges"><span class="badge" :data-status="selected.status">{{ statusLabels[selected.status] }}</span><span class="badge" :data-sla="selected.sla_state">{{ slaLabels[selected.sla_state] }}</span></div>
        </div>
        <dl class="detail-grid">
          <div><dt>候选 ID</dt><dd><code>{{ selected.candidate_id }}</code></dd></div>
          <div><dt>检测规则</dt><dd><code>{{ selected.rule_version }}</code></dd></div>
          <div><dt>SLA 规则</dt><dd><code>{{ selected.sla_rule_version }}</code></dd></div>
          <div><dt>负责人</dt><dd>{{ selected.assigned_to_username || "未指派" }}</dd></div>
          <div><dt>独立失败数</dt><dd>{{ selected.independent_failure_count }}</dd></div>
          <div><dt>失败权重</dt><dd>{{ selected.failure_weight }}</dd></div>
          <div><dt>响应截止</dt><dd>{{ formatTime(selected.acknowledge_due_at) }}</dd></div>
          <div><dt>首次响应</dt><dd>{{ formatTime(selected.acknowledged_at) }}</dd></div>
          <div><dt>解决截止</dt><dd>{{ formatTime(selected.resolve_due_at) }}</dd></div>
          <div><dt>解决时间</dt><dd>{{ formatTime(selected.resolved_at) }}</dd></div>
          <div><dt>观察窗口开始</dt><dd>{{ formatTime(selected.window_started_at) }}</dd></div>
          <div><dt>观察窗口结束</dt><dd>{{ formatTime(selected.window_ended_at) }}</dd></div>
          <div><dt>处理结果</dt><dd>{{ selected.resolution_code || "—" }}</dd></div>
        </dl>
        <section v-if="selected.resolution_note"><h3>处理说明</h3><p class="note">{{ selected.resolution_note }}</p></section>

        <section v-if="selected.status !== 'resolved'" class="action-box">
          <h3>负责人指派</h3>
          <label>具备 MFA 的值班人员<select v-model="assigneeId"><option value="" disabled>请选择负责人</option><option v-for="operator in operators" :key="operator.id" :value="operator.id">{{ operator.username }} · {{ operator.role }}</option></select></label>
          <label>指派说明（不要粘贴敏感标识）<textarea v-model="assignmentNote" maxlength="1000" rows="2" /></label>
          <div class="actions"><button class="button secondary" :disabled="busy || !assigneeId || assigneeId === selected.assigned_to_id" @click="applyAssignment">更新负责人</button></div>
        </section>

        <section class="action-box">
          <h3>告警处置</h3>
          <label>处理说明（不要粘贴密码、令牌、IP 或安装标识）<textarea v-model="resolutionNote" maxlength="1000" rows="3" /></label>
          <div class="actions"><button v-for="action in actions" :key="action.code" class="button" :class="{ danger: action.danger }" :disabled="busy" @click="applyAction(action)">{{ action.label }}</button></div>
        </section>

        <section><h3>通知投递记录</h3><p v-if="selected.notifications.length === 0" class="empty">暂无通知记录。</p><ol v-else class="timeline"><li v-for="notification in selected.notifications" :key="notification.id"><strong>{{ notificationLabels[notification.kind] }} · {{ notificationStatusLabels[notification.status] }}</strong><p>接收人 {{ notification.recipient_username }} · 尝试 {{ notification.attempts }} 次</p><small>{{ formatTime(notification.sent_at || notification.available_at) }}<template v-if="notification.last_error_code"> · {{ notification.last_error_code }}</template></small></li></ol></section>

        <section><h3>不可变告警时间线</h3><ol class="timeline"><li v-for="event in selected.events" :key="event.id"><strong>{{ event.action }}</strong><p>{{ event.previous_status || "检测" }} → {{ event.next_status }} · {{ event.reason_code }}</p><p v-if="event.previous_assignee_id !== event.next_assignee_id">负责人：{{ operatorName(event.previous_assignee_id) }} → {{ operatorName(event.next_assignee_id) }}</p><p v-if="event.note">{{ event.note }}</p><small>{{ formatTime(event.created_at) }} · {{ event.request_id || "系统检测" }}</small></li></ol></section>
      </article>
      <article v-else class="panel empty">请选择左侧告警查看详情。</article>
    </div>
  </section>
</template>

<style scoped>
.risk-page { display: grid; gap: 18px; }
.page-heading, .detail-title, .alert-row span, .actions, .badges { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
.page-heading h1, .detail-title h2 { margin: 4px 0; }.page-heading p { margin: 0; color: var(--muted); }.eyebrow { color: #b42318 !important; font-size: 12px; font-weight: 800; letter-spacing: .08em; }
.filters { display: flex; gap: 12px; align-items: end; flex-wrap: wrap; }.filters label, .action-box label { display: grid; gap: 6px; color: var(--muted); font-size: 13px; font-weight: 700; }.filters select, .filters input, .action-box select, textarea { box-sizing: border-box; width: 100%; padding: 11px 13px; border: 1px solid var(--border); border-radius: 10px; background: white; font: inherit; }.filters .query { flex: 1; min-width: 250px; }.filters .check { display: flex; align-items: center; padding: 10px 0; }.filters .check input { width: auto; }
.risk-layout { display: grid; grid-template-columns: minmax(300px, .72fr) minmax(0, 1.28fr); gap: 18px; align-items: start; }.alert-list { display: grid; gap: 10px; max-height: calc(100vh - 220px); overflow: auto; }.alert-row { display: grid; gap: 8px; padding: 14px; text-align: left; border: 1px solid var(--border); border-radius: 12px; background: white; cursor: pointer; }.alert-row.selected, .alert-row:hover { border-color: #f04438; background: #fff5f4; }.alert-row code, .alert-row small { color: var(--muted); overflow-wrap: anywhere; }
.badges { justify-content: flex-end; flex-wrap: wrap; }.badge { padding: 4px 9px; border-radius: 999px; background: #e2e8f0; font-size: 12px; font-weight: 800; }.badge[data-status="open"], .badge[data-sla="acknowledgement_overdue"], .badge[data-sla="resolution_overdue"], .badge[data-sla="breached"] { background: #fef3f2; color: #b42318; }.badge[data-status="acknowledged"], .badge[data-sla="within_sla"] { background: #fff7ed; color: #9a3412; }.badge[data-status="resolved"], .badge[data-sla="met"] { background: #ecfdf3; color: #067647; }
.detail { display: grid; gap: 18px; }.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 0; }.detail-grid dt { color: var(--muted); font-size: 12px; font-weight: 700; }.detail-grid dd { margin: 4px 0 0; overflow-wrap: anywhere; }.note { padding: 13px; border-radius: 10px; background: #f8fafc; white-space: pre-wrap; }.action-box { display: grid; gap: 12px; padding: 15px; border-radius: 12px; background: #f8fafc; }.action-box h3 { margin: 0; }.actions { justify-content: flex-start; flex-wrap: wrap; }.button.danger { background: #b42318; }.button.secondary { background: #475467; }.timeline { display: grid; gap: 12px; padding-left: 20px; }.timeline li { padding-left: 8px; }.timeline p { margin: 5px 0; }.timeline small, .empty { color: var(--muted); }
@media (max-width: 900px) { .risk-layout { grid-template-columns: 1fr; }.alert-list { max-height: none; } } @media (max-width: 600px) { .detail-grid { grid-template-columns: 1fr; } }
</style>
