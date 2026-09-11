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
import { allAdminNavigationItems } from "@/lib/adminNavigation";
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
      tone: "bg-primary/10 text-primary",
    },
    {
      label: "查询命中率",
      value: formatPercent(summary.value.search_hit_rate),
      detail: "按检索审计事件计算",
      icon: DatabaseZap,
      tone: "bg-accent/10 text-accent",
    },
    {
      label: "新增贡献",
      value: formatInteger(summary.value.contribution_count),
      detail: `${summary.value.window_hours} 小时窗口`,
      icon: Activity,
      tone: "bg-secondary text-secondary-foreground",
    },
    {
      label: "候选验证率",
      value: formatPercent(summary.value.candidate_verification_rate),
      detail: `${formatInteger(summary.value.verified_candidate_count)} / ${formatInteger(summary.value.candidate_count)}`,
      icon: ShieldCheck,
      tone: "bg-[hsl(var(--success)/0.12)] text-[hsl(var(--success))]",
    },
    {
      label: "隔离候选",
      value: formatInteger(summary.value.quarantined_candidate_count),
      detail: "当前状态快照",
      icon: CircleAlert,
      tone: "bg-[hsl(var(--warning)/0.12)] text-[hsl(var(--warning))]",
    },
    {
      label: "审计失败率",
      value: formatPercent(summary.value.audited_error_rate),
      detail: `${formatInteger(summary.value.audited_error_count)} / ${formatInteger(summary.value.audited_operation_count)}`,
      icon: ClipboardCheck,
      tone: "bg-destructive/10 text-destructive",
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
    <header class="glass overflow-hidden rounded-3xl p-6 md:p-8">
      <div class="flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
        <div class="max-w-3xl space-y-3">
          <div class="text-xs font-semibold uppercase tracking-[0.24em] text-primary">N2 · 安全运营工作台</div>
          <h1 class="text-3xl font-semibold tracking-tight text-foreground md:text-4xl">运营仪表盘</h1>
          <p class="max-w-2xl text-sm leading-6 text-muted-foreground md:text-base">
            聚合检索、贡献、候选状态、审计失败与治理队列；所有卡片均来自服务端实时统计，不使用前端硬编码业务数据。
          </p>
        </div>
        <div v-if="summary" class="rounded-2xl border border-border bg-muted/60 px-4 py-3 text-sm text-muted-foreground">
          <div class="font-medium text-foreground">近 {{ summary.window_hours }} 小时</div>
          <div class="mt-1 text-xs">生成于 {{ formatTimestamp(summary.generated_at) }}</div>
        </div>
      </div>
    </header>

    <div v-if="error" role="alert" class="rounded-2xl border border-destructive/30 bg-destructive/10 px-5 py-4 text-sm text-destructive">
      {{ error }}
    </div>

    <div v-if="loading" aria-live="polite" class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      <div v-for="index in 6" :key="index" class="glass h-36 animate-pulse rounded-2xl" />
    </div>

    <div v-else-if="summary" class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      <article v-for="metric in metrics" :key="metric.label" class="glass rounded-2xl p-5">
        <div class="flex items-start justify-between gap-4">
          <div>
            <p class="text-sm font-medium text-muted-foreground">{{ metric.label }}</p>
            <p class="mt-3 text-3xl font-semibold tracking-tight text-foreground">{{ metric.value }}</p>
            <p class="mt-2 text-xs text-muted-foreground">{{ metric.detail }}</p>
          </div>
          <span class="rounded-2xl p-3" :class="metric.tone">
            <component :is="metric.icon" class="h-5 w-5" aria-hidden="true" />
          </span>
        </div>
      </article>
    </div>

    <div v-if="summary" class="grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
      <section class="glass rounded-3xl p-6">
        <div class="flex items-center justify-between gap-4">
          <div>
            <p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">Queue backlog</p>
            <h2 class="mt-2 text-xl font-semibold text-foreground">治理待办队列</h2>
          </div>
          <div class="btn-gradient rounded-2xl px-4 py-2 text-2xl font-semibold">{{ formatInteger(summary.queue_backlog.total) }}</div>
        </div>
        <div class="mt-6 divide-y divide-border">
          <RouterLink v-for="item in queueItems" :key="item.label" :to="item.to" class="flex items-center justify-between gap-4 py-3 text-sm transition hover:text-primary">
            <span class="text-muted-foreground">{{ item.label }}</span>
            <span class="font-semibold text-foreground">{{ formatInteger(item.value) }}</span>
          </RouterLink>
        </div>
      </section>

      <section class="glass rounded-3xl p-6">
        <p class="text-xs font-semibold uppercase tracking-[0.2em] text-primary">Metric contract</p>
        <h2 class="mt-2 text-xl font-semibold text-foreground">口径说明</h2>
        <ul class="mt-5 space-y-3 text-sm leading-6 text-muted-foreground">
          <li>查询指标自本切片上线后由脱敏审计事件累计，不保存用户提交的完整指纹。</li>
          <li>候选验证率与隔离数为当前状态快照；新增贡献、查询与审计失败率按 24 小时窗口统计。</li>
          <li>审计失败率仅代表已审计业务操作结果，不等同于全量 HTTP 请求错误率。</li>
        </ul>
      </section>
    </div>

    <section class="glass rounded-3xl p-6 md:p-8" aria-labelledby="admin-paths-title">
      <div class="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <p class="text-xs font-semibold uppercase tracking-[0.2em] text-primary">Internal routes</p>
          <h2 id="admin-paths-title" class="mt-2 text-2xl font-semibold text-foreground">全部管理功能站内路径</h2>
          <p class="mt-2 text-sm leading-6 text-muted-foreground">集中展示管理端已注册功能及站内地址，可直接进入对应工作台。</p>
        </div>
        <span class="text-sm font-medium text-muted-foreground">共 {{ allAdminNavigationItems.length }} 个入口</span>
      </div>

      <div class="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <RouterLink
          v-for="item in allAdminNavigationItems"
          :key="item.path"
          :to="item.path"
          class="group rounded-2xl border border-border bg-card/50 p-4 text-inherit transition hover:-translate-y-0.5 hover:border-primary/40 hover:bg-card hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        >
          <div class="flex items-start gap-3">
            <span class="rounded-xl bg-primary/10 p-2 text-primary shadow-sm transition group-hover:bg-primary/15">
              <component :is="item.icon" class="size-4" aria-hidden="true" />
            </span>
            <span class="min-w-0">
              <span class="block font-semibold text-foreground">{{ item.label }}</span>
              <span class="mt-1 block font-mono text-xs font-medium text-primary">{{ item.path }}</span>
              <span class="mt-2 block text-xs leading-5 text-muted-foreground">{{ item.description }}</span>
            </span>
          </div>
        </RouterLink>
      </div>
    </section>
  </section>
</template>
