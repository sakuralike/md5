<script setup lang="ts">
import type {
  AlgorithmDistributionResponse,
  CommunityActivityTrendResponse,
} from "@password-detective/api-contract";
import { Activity, BarChart3, RefreshCw, ShieldCheck } from "lucide-vue-next";
import { onMounted, ref } from "vue";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  getAlgorithmDistribution,
  getCommunityActivityTrend,
} from "../services/site";

const data = ref<AlgorithmDistributionResponse | null>(null);
const trend = ref<CommunityActivityTrendResponse | null>(null);
const windowDays = ref("30");
const loading = ref(false);
const error = ref("");
const algorithmLabels = { md5: "MD5", sha1: "SHA-1", sha256: "SHA-256", sha512: "SHA-512" } as const;

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const [distribution, activityTrend] = await Promise.all([
      getAlgorithmDistribution(),
      getCommunityActivityTrend(Number(windowDays.value)),
    ]);
    data.value = distribution;
    trend.value = activityTrend;
  } catch (value) {
    error.value = value instanceof Error ? value.message : "统计数据暂时不可用";
  } finally {
    loading.value = false;
  }
}

function bandProgress(band: string): number {
  if (band === "0") return 0;
  if (band === "少于 10") return 15;
  if (band === "10-49") return 35;
  if (band === "50-99") return 55;
  if (band === "100-499") return 75;
  if (band === "500-999") return 90;
  return 100;
}

function formatDay(day: string): string {
  const [, month, date] = day.split("-");
  return `${month}-${date}`;
}

onMounted(() => void load());
</script>

<template>
  <main class="mx-auto w-full max-w-5xl space-y-8 px-4 py-8 sm:px-6">
    <header class="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div class="space-y-2">
        <div class="flex items-center gap-2 text-sm font-medium text-primary">
          <BarChart3 class="h-4 w-4" />公开数据统计
        </div>
        <h1 class="text-3xl font-semibold">算法分布</h1>
        <p class="max-w-2xl text-sm leading-6 text-muted-foreground">
          仅聚合已验证公开档案的指纹算法，不包含待验证、隔离记录或任何候选密码。
        </p>
      </div>
      <Button variant="outline" :disabled="loading" @click="load">
        <RefreshCw class="mr-2 h-4 w-4" :class="loading && 'animate-spin'" />刷新
      </Button>
    </header>

    <p v-if="error" class="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive" role="alert">{{ error }}</p>

    <section class="space-y-5 border-y py-6" aria-labelledby="activity-heading">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div class="flex items-center gap-2 text-sm font-medium text-primary">
            <Activity class="h-4 w-4" />社区活跃度趋势
          </div>
          <h2 id="activity-heading" class="mt-2 text-lg font-semibold">公开社区热度</h2>
          <p class="mt-1 text-sm text-muted-foreground">仅展示时间桶和数量区间，不展示主题、评论或用户明细。</p>
        </div>
        <div class="flex items-center gap-2">
          <span class="text-sm text-muted-foreground">时间范围</span>
          <Select v-model="windowDays" @update:model-value="load">
            <SelectTrigger aria-label="统计时间范围" class="w-28"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="7">近 7 天</SelectItem>
              <SelectItem value="30">近 30 天</SelectItem>
              <SelectItem value="90">近 90 天</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
      <div v-if="loading && !trend" class="grid gap-3 sm:grid-cols-3" aria-label="正在加载社区活跃度">
        <div v-for="index in 3" :key="index" class="h-20 animate-pulse rounded-md bg-muted" />
      </div>
      <template v-else-if="trend">
        <div class="grid gap-3 sm:grid-cols-3">
          <div class="rounded-md border bg-card p-4">
            <p class="text-xs text-muted-foreground">最新日期桶</p>
            <p class="mt-2 font-semibold">{{ trend.buckets.at(-1)?.day ?? "暂无" }}</p>
            <p class="mt-1 text-xs text-muted-foreground">活跃度 {{ trend.buckets.at(-1)?.activity_count_band ?? "0" }}</p>
          </div>
          <div class="rounded-md border bg-card p-4">
            <p class="text-xs text-muted-foreground">活跃板块区间</p>
            <p class="mt-2 font-semibold">{{ trend.buckets.at(-1)?.active_boards_count_band ?? "0" }}</p>
            <p class="mt-1 text-xs text-muted-foreground">按最新日期桶统计</p>
          </div>
          <div class="rounded-md border bg-card p-4">
            <p class="text-xs text-muted-foreground">统计窗口</p>
            <p class="mt-2 font-semibold">近 {{ trend.window_days }} 天</p>
            <p class="mt-1 text-xs text-muted-foreground">数据已做隐私分桶</p>
          </div>
        </div>
        <div class="space-y-3">
          <div v-for="bucket in trend.buckets" :key="bucket.day" class="grid grid-cols-[3.5rem_minmax(0,1fr)_5rem] items-center gap-3 text-sm">
            <span class="font-mono text-xs text-muted-foreground">{{ formatDay(bucket.day) }}</span>
            <Progress :model-value="bandProgress(bucket.activity_count_band)" :aria-label="`${bucket.day} 活跃度 ${bucket.activity_count_band}`" />
            <span class="text-right text-xs text-muted-foreground">{{ bucket.activity_count_band }}</span>
          </div>
        </div>
        <div class="space-y-3 border-t pt-5">
          <div class="flex items-center justify-between gap-3">
            <h3 class="font-semibold">板块热度</h3>
            <Badge variant="secondary"><ShieldCheck class="mr-1 h-3.5 w-3.5" />聚合区间</Badge>
          </div>
          <div v-for="board in trend.boards" :key="board.board_code" class="space-y-2">
            <div class="flex items-center justify-between gap-4 text-sm">
              <span class="font-medium">{{ board.board_name }}</span>
              <span class="text-muted-foreground">{{ board.activity_count_band }}</span>
            </div>
            <Progress :model-value="bandProgress(board.activity_count_band)" :aria-label="`${board.board_name} 活跃度 ${board.activity_count_band}`" />
          </div>
          <p v-if="trend.boards.length === 0" class="text-sm text-muted-foreground">暂无公开板块统计。</p>
        </div>
      </template>
    </section>

    <section class="space-y-5 border-y py-6" aria-labelledby="distribution-heading">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="distribution-heading" class="text-lg font-semibold">公开指纹池</h2>
          <p class="mt-1 text-sm text-muted-foreground">总量区间：{{ data?.total_count_band ?? "读取中" }}</p>
        </div>
        <Badge variant="secondary"><ShieldCheck class="mr-1 h-3.5 w-3.5" />隐私聚合</Badge>
      </div>
      <div v-if="loading && !data" class="space-y-4" aria-label="正在加载算法分布">
        <div v-for="index in 4" :key="index" class="h-14 animate-pulse rounded-md bg-muted" />
      </div>
      <div v-else-if="data" class="space-y-5">
        <div v-for="item in data.items" :key="item.algorithm" class="space-y-2">
          <div class="flex items-center justify-between gap-4 text-sm">
            <span class="font-medium">{{ algorithmLabels[item.algorithm] }}</span>
            <span class="text-muted-foreground">{{ item.count_band }} · {{ item.percentage }}%</span>
          </div>
          <Progress :model-value="item.percentage" :aria-label="`${algorithmLabels[item.algorithm]} 占比 ${item.percentage}%`" />
        </div>
      </div>
    </section>
  </main>
</template>
