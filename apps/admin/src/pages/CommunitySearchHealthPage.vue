<script setup lang="ts">
import {
  ApiError,
  type CommunitySearchHealthResponse,
  type CommunitySearchRebuildStatus,
} from "@password-detective/api-contract";
import { computed, onMounted, ref } from "vue";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { getCommunitySearchHealth } from "../services/communitySearch";
import { useAdminAuthStore } from "../stores/auth";

const auth = useAdminAuthStore();
const health = ref<CommunitySearchHealthResponse | null>(null);
const loading = ref(true);
const error = ref("");

const latencyBuckets = computed(() =>
  Object.entries(health.value?.delivery_latency_buckets ?? {}).sort(([left], [right]) =>
    left.localeCompare(right),
  ),
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
  return value instanceof Error ? value.message : "加载社区搜索健康状态失败";
}

async function refresh(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    health.value = await getCommunitySearchHealth(token());
  } catch (caught) {
    error.value = describeError(caught);
  } finally {
    loading.value = false;
  }
}

function formatInteger(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}

function formatTimestamp(value: string | null): string {
  if (!value) return "暂无";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatDuration(value: number | null): string {
  if (value === null) return "暂无待处理事件";
  if (value < 60) return `${value} 秒`;
  if (value < 3600) return `${Math.floor(value / 60)} 分钟`;
  return `${Math.floor(value / 3600)} 小时`;
}

function rebuildStatusLabel(status: CommunitySearchRebuildStatus): string {
  const labels: Record<CommunitySearchRebuildStatus, string> = {
    pending: "等待执行",
    running: "执行中",
    completed: "已完成",
    failed: "失败",
  };
  return labels[status];
}
</script>

<template>
  <section class="space-y-6">
    <div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div class="space-y-1">
        <div class="flex flex-wrap items-center gap-2">
          <h1 class="text-2xl font-semibold tracking-tight text-foreground">社区搜索健康</h1>
          <Badge v-if="health" variant="secondary">{{ health.provider.mode }}</Badge>
          <Badge v-if="health?.provider.degraded" variant="destructive">已降级</Badge>
        </div>
        <p class="text-sm text-muted-foreground">
          仅展示 Provider、索引 Outbox 与重建的匿名聚合指标，不展示内容、用户或检索记录。
        </p>
      </div>
      <Button type="button" :disabled="loading" @click="refresh">
        {{ loading ? "刷新中…" : "刷新状态" }}
      </Button>
    </div>

    <div
      v-if="error"
      role="alert"
      class="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive"
    >
      {{ error }}
    </div>

    <div
      v-if="health?.provider.degraded"
      class="rounded-lg border border-primary/40 bg-muted px-4 py-3 text-sm text-foreground"
    >
      当前 Provider 正在使用受上限的降级模式；请按运维流程检查目标数据库 ngram 能力与索引状态。
    </div>

    <p v-if="loading && !health" class="text-sm text-muted-foreground">正在加载聚合健康状态…</p>

    <template v-else-if="health">
      <p class="text-xs text-muted-foreground">数据生成于 {{ formatTimestamp(health.generated_at) }}</p>

      <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <article class="rounded-xl border bg-card p-4 text-card-foreground shadow-sm">
          <p class="text-sm text-muted-foreground">待处理 Outbox</p>
          <p class="mt-2 text-2xl font-semibold">{{ formatInteger(health.pending_count) }}</p>
          <p class="mt-1 text-xs text-muted-foreground">最早等待：{{ formatDuration(health.oldest_pending_seconds) }}</p>
        </article>
        <article class="rounded-xl border bg-card p-4 text-card-foreground shadow-sm">
          <p class="text-sm text-muted-foreground">投递失败</p>
          <p class="mt-2 text-2xl font-semibold">{{ formatInteger(health.failed_count) }}</p>
          <p class="mt-1 text-xs text-muted-foreground">到期可重试：{{ formatInteger(health.retry_due_count) }}</p>
        </article>
        <article class="rounded-xl border bg-card p-4 text-card-foreground shadow-sm">
          <p class="text-sm text-muted-foreground">累计投递</p>
          <p class="mt-2 text-2xl font-semibold">{{ formatInteger(health.delivered_count) }}</p>
          <p class="mt-1 text-xs text-muted-foreground">最近成功：{{ formatTimestamp(health.last_delivered_at) }}</p>
        </article>
        <article class="rounded-xl border bg-card p-4 text-card-foreground shadow-sm">
          <p class="text-sm text-muted-foreground">Provider 状态</p>
          <p class="mt-2 text-2xl font-semibold">{{ health.provider.mode }}</p>
          <p class="mt-1 text-xs text-muted-foreground">
            {{ health.provider.degraded ? "受限降级检索" : "正常检索能力" }}
          </p>
        </article>
      </div>

      <div class="grid gap-4 lg:grid-cols-2">
        <article class="rounded-xl border bg-card p-5 text-card-foreground shadow-sm">
          <h2 class="text-base font-semibold">近 24 小时投递延迟</h2>
          <dl v-if="latencyBuckets.length" class="mt-4 divide-y">
            <div v-for="[bucket, count] in latencyBuckets" :key="bucket" class="flex items-center justify-between py-3 text-sm">
              <dt class="text-muted-foreground">{{ bucket }}</dt>
              <dd class="font-medium">{{ formatInteger(count) }}</dd>
            </div>
          </dl>
          <p v-else class="mt-4 text-sm text-muted-foreground">暂无投递延迟聚合数据。</p>
        </article>

        <article class="rounded-xl border bg-card p-5 text-card-foreground shadow-sm">
          <h2 class="text-base font-semibold">最近索引重建</h2>
          <template v-if="health.last_rebuild">
            <div class="mt-4 flex items-center gap-2">
              <Badge variant="secondary">{{ rebuildStatusLabel(health.last_rebuild.status) }}</Badge>
              <span class="text-xs text-muted-foreground">
                开始于 {{ formatTimestamp(health.last_rebuild.started_at) }}
              </span>
            </div>
            <dl class="mt-4 grid grid-cols-2 gap-3 text-sm">
              <div class="rounded-lg bg-muted p-3">
                <dt class="text-muted-foreground">预期文档</dt>
                <dd class="mt-1 font-semibold">{{ formatInteger(health.last_rebuild.expected_count) }}</dd>
              </div>
              <div class="rounded-lg bg-muted p-3">
                <dt class="text-muted-foreground">已索引</dt>
                <dd class="mt-1 font-semibold">{{ formatInteger(health.last_rebuild.indexed_count) }}</dd>
              </div>
              <div class="rounded-lg bg-muted p-3">
                <dt class="text-muted-foreground">缺失</dt>
                <dd class="mt-1 font-semibold">{{ formatInteger(health.last_rebuild.missing_count) }}</dd>
              </div>
              <div class="rounded-lg bg-muted p-3">
                <dt class="text-muted-foreground">多余</dt>
                <dd class="mt-1 font-semibold">{{ formatInteger(health.last_rebuild.extra_count) }}</dd>
              </div>
            </dl>
            <p class="mt-4 text-xs text-muted-foreground">
              完成于 {{ formatTimestamp(health.last_rebuild.finished_at) }}
            </p>
          </template>
          <p v-else class="mt-4 text-sm text-muted-foreground">尚无索引重建运行记录。</p>
        </article>
      </div>
    </template>
  </section>
</template>
