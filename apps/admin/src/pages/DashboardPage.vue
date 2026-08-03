<script setup lang="ts">
import type { AdminDashboardSummary } from "@password-detective/api-contract";
import {
  Activity,
  Search,
  CircleAlert,
  ClipboardCheck,
  DatabaseZap,
  ShieldCheck,
} from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";
import { getAdminDashboardSummary } from "../services/dashboard";
import { useAdminAuthStore } from "../stores/auth";

const auth = useAdminAuthStore();
const summary = ref<AdminDashboardSummary | null>(null);
const loading = ref(true);
const error = ref("");

function formatInteger(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}

function formatPercent(value: number): string {
  return new Intl.NumberFormat("zh-CN", {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(value);
}

function formatTimestamp(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

const metrics = computed(() => {
  if (!summary.value) return [];
  return [
    {
      label: "有效查询",
      value: formatInteger(summary.value.search_count),
      detail: `命中 ${formatInteger(summary.value.search_hit_count)} 次`,
      icon: Search,
      tone: "text-sky-700 bg-sky-50",
    },
    {
      label: "查询命中率",
      value: formatPercent(summary.value.search_hit_rate),
      detail: "按检索审计事件计算",
      icon: DatabaseZap,
      tone: "text-cyan-700 bg-cyan-50",
    },
    {
      label: "新增贡献",
      value: formatInteger(summary.value.contribution_count),
      detail: `${summary.value.window_hours} 小时窗口`,
      icon: Activity,
      tone: "text-indigo-700 bg-indigo-50",
    },
    {
      label: "候选验证率",
      value: formatPercent(summary.value.candidate_verification_rate),
      detail: `${formatInteger(summary.value.verified_candidate_count)} / ${formatInteger(summary.value.candidate_count)}`,
      icon: ShieldCheck,
      tone: "text-emerald-700 bg-emerald-50",
    },
    {
      label: "隔离候选",
      value: formatInteger(summary.value.quarantined_candidate_count),
      detail: "当前状态快照",
      icon: CircleAlert,
      tone: "text-amber-700 bg-amber-50",
    },
    {
      label: "审计失败率",
      value: formatPercent(summary.value.audited_error_rate),
      detail: `${formatInteger(summary.value.audited_error_count)} / ${formatInteger(summary.value.audited_operation_count)}`,
      icon: ClipboardCheck,
      tone: "text-rose-700 bg-rose-50",
    },
  ];
});

const queueItems = computed(() => {
  if (!summary.value) return [];
  const queue = summary.value.queue_backlog;
  return [
    { label: "待审核候选", value: queue.pending_candidates, to: "/candidates" },
    { label: "处理中举报申诉", value: queue.active_trust_cases, to: "/trust-cases" },
    { label: "未关闭风险告警", value: queue.active_risk_alerts, to: "/risk-alerts" },
    { label: "待处理隐私导出", value: queue.pending_privacy_exports, to: "/audit" },
    { label: "待处理账号删除", value: queue.pending_deletion_requests, to: "/audit" },
  ];
});

async function loadSummary(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    summary.value = await getAdminDashboardSummary(auth.accessToken, 24);
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "仪表盘指标加载失败";
  } finally {
    loading.value = false;
  }
}

onMounted(loadSummary);
</script>

<template>
  <section class="space-y-6">
    <header class="overflow-hidden rounded-3xl border border-white/70 bg-white/75 p-6 shadow-sm shadow-slate-200/70 backdrop-blur-xl md:p-8">
      <div class="flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
        <div class="max-w-3xl space-y-3">
          <div class="text-xs font-semibold uppercase tracking-[0.24em] text-sky-700">N2 · 安全运营工作台</div>
          <h1 class="text-3xl font-semibold tracking-tight text-slate-950 md:text-4xl">真实指标仪表盘</h1>
          <p class="max-w-2xl text-sm leading-6 text-slate-600 md:text-base">
            聚合检索、贡献、候选状态、审计失败与治理队列；所有卡片均来自服务端实时统计，不使用前端硬编码业务数据。
          </p>
        </div>
        <div v-if="summary" class="rounded-2xl border border-slate-200/80 bg-slate-50/80 px-4 py-3 text-sm text-slate-600">
          <div class="font-medium text-slate-900">近 {{ summary.window_hours }} 小时</div>
          <div class="mt-1 text-xs">生成于 {{ formatTimestamp(summary.generated_at) }}</div>
        </div>
      </div>
    </header>

    <div v-if="error" role="alert" class="rounded-2xl border border-rose-200 bg-rose-50/90 px-5 py-4 text-sm text-rose-800">
      {{ error }}
    </div>

    <div v-if="loading" aria-live="polite" class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      <div v-for="index in 6" :key="index" class="h-36 animate-pulse rounded-2xl border border-white/70 bg-white/65 shadow-sm backdrop-blur-xl" />
    </div>

    <div v-else-if="summary" class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      <article v-for="metric in metrics" :key="metric.label" class="rounded-2xl border border-white/70 bg-white/80 p-5 shadow-sm shadow-slate-200/70 backdrop-blur-xl">
        <div class="flex items-start justify-between gap-4">
          <div>
            <p class="text-sm font-medium text-slate-500">{{ metric.label }}</p>
            <p class="mt-3 text-3xl font-semibold tracking-tight text-slate-950">{{ metric.value }}</p>
            <p class="mt-2 text-xs text-slate-500">{{ metric.detail }}</p>
          </div>
          <span class="rounded-2xl p-3" :class="metric.tone">
            <component :is="metric.icon" class="h-5 w-5" aria-hidden="true" />
          </span>
        </div>
      </article>
    </div>

    <div v-if="summary" class="grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
      <section class="rounded-3xl border border-white/70 bg-white/80 p-6 shadow-sm shadow-slate-200/70 backdrop-blur-xl">
        <div class="flex items-center justify-between gap-4">
          <div>
            <p class="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Queue backlog</p>
            <h2 class="mt-2 text-xl font-semibold text-slate-950">治理待办队列</h2>
          </div>
          <div class="rounded-2xl bg-slate-950 px-4 py-2 text-2xl font-semibold text-white">{{ formatInteger(summary.queue_backlog.total) }}</div>
        </div>
        <div class="mt-6 divide-y divide-slate-100">
          <RouterLink v-for="item in queueItems" :key="item.label" :to="item.to" class="flex items-center justify-between gap-4 py-3 text-sm transition hover:text-sky-700">
            <span class="text-slate-600">{{ item.label }}</span>
            <span class="font-semibold text-slate-950">{{ formatInteger(item.value) }}</span>
          </RouterLink>
        </div>
      </section>

      <section class="rounded-3xl border border-sky-100 bg-gradient-to-br from-white/90 to-sky-50/80 p-6 shadow-sm shadow-sky-100/70 backdrop-blur-xl">
        <p class="text-xs font-semibold uppercase tracking-[0.2em] text-sky-700">Metric contract</p>
        <h2 class="mt-2 text-xl font-semibold text-slate-950">口径说明</h2>
        <ul class="mt-5 space-y-3 text-sm leading-6 text-slate-600">
          <li>查询指标自本切片上线后由脱敏审计事件累计，不保存用户提交的完整指纹。</li>
          <li>候选验证率与隔离数为当前状态快照；新增贡献、查询与审计失败率按 24 小时窗口统计。</li>
          <li>审计失败率仅代表已审计业务操作结果，不等同于全量 HTTP 请求错误率。</li>
        </ul>
      </section>
    </div>

    <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <RouterLink class="rounded-2xl border border-white/70 bg-white/70 p-5 text-inherit shadow-sm backdrop-blur-xl transition hover:-translate-y-0.5 hover:shadow-md" to="/candidates">
        <span class="text-xs font-semibold text-emerald-700">M4 已接入</span><h2 class="mt-2 font-semibold text-slate-950">候选审核</h2><p class="mt-2 text-sm leading-6 text-slate-500">查看证据时间线并执行可审计状态处置。</p>
      </RouterLink>
      <RouterLink class="rounded-2xl border border-white/70 bg-white/70 p-5 text-inherit shadow-sm backdrop-blur-xl transition hover:-translate-y-0.5 hover:shadow-md" to="/risk-alerts">
        <span class="text-xs font-semibold text-amber-700">M4 已接入</span><h2 class="mt-2 font-semibold text-slate-950">风险告警</h2><p class="mt-2 text-sm leading-6 text-slate-500">处理失败激增告警、分派和通知回放。</p>
      </RouterLink>
      <RouterLink class="rounded-2xl border border-white/70 bg-white/70 p-5 text-inherit shadow-sm backdrop-blur-xl transition hover:-translate-y-0.5 hover:shadow-md" to="/desktop-releases">
        <span class="text-xs font-semibold text-sky-700">M3 已接入</span><h2 class="mt-2 font-semibold text-slate-950">桌面发布</h2><p class="mt-2 text-sm leading-6 text-slate-500">管理发布草稿、制品校验、发布与撤回。</p>
      </RouterLink>
      <RouterLink class="rounded-2xl border border-dashed border-slate-300 bg-white/55 p-5 text-inherit shadow-sm backdrop-blur-xl transition hover:-translate-y-0.5 hover:shadow-md" to="/audit">
        <span class="text-xs font-semibold text-slate-500">N2 下一切片</span><h2 class="mt-2 font-semibold text-slate-950">审计查询</h2><p class="mt-2 text-sm leading-6 text-slate-500">继续接入列表、详情与 CSV 导出。</p>
      </RouterLink>
    </div>
  </section>
</template>
